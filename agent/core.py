"""Fill In - the agent itself.

Two things live here and nothing else: which model backs the agent, and the
system prompt. Everything the agent is *allowed* to do lives in agent/tools.py,
where the hard rules are return statements rather than sentences - a model can
argue with a prompt, but not with a refusal.
"""

import os
import sys

from strands import Agent

from agent.db import query, log_event
from agent.tools import (
    TOOLS,
    ASK_TIMEOUT_MINUTES,
    MAX_ASKS_PER_SHIFT,
    URGENT_WINDOW_HOURS,
)

# --------------------------------------------------------------- provider ----
#
# The hackathon requires Strands, not Bedrock or any particular model. Three
# providers are wired up so the demo is never blocked on an IAM console or a
# credit card: set FILLIN_PROVIDER to pick one, or leave it unset and whichever
# credentials exist win. Gemini's free tier needs neither.

DEFAULT_MODEL = {
    # The demo script was verified end to end on this one, and it is the fastest
    # on the free tier. gemini-3.8-flash returned "high demand" 503s in testing.
    "gemini": "gemini-3.5-flash-lite",
    # Amazon's own model, billed as Amazon Bedrock itself, so AWS credits apply.
    # Anthropic models on Bedrock can be billed through AWS Marketplace instead,
    # which promotional credits do not cover. Nova 2 Lite ran the demo cleanly.
    "bedrock": "us.amazon.nova-2-lite-v1:0",
    "anthropic": "claude-sonnet-5",
}

SETUP_HINT = """
No working model credentials found.

Pick one of these:

  Gemini (free tier)     pip install "strands-agents[gemini]"
                         create a key at https://aistudio.google.com/apikey
                         setx GEMINI_API_KEY "your-key"
                         setx FILLIN_PROVIDER gemini

  Bedrock (AWS)          set AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY and
                         AWS_DEFAULT_REGION=us-east-1, on an IAM user with
                         AmazonBedrockFullAccess, and enable model access for
                         the model in the Bedrock console for that region.

  Anthropic API          pip install "strands-agents[anthropic]"
                         set ANTHROPIC_API_KEY
                         set FILLIN_PROVIDER=anthropic

Override the model with FILLIN_MODEL - for example gemini-3.8-flash for a
stronger Gemini, or claude-haiku-4-5 to iterate cheaply on the Anthropic API.
""".strip()


class ProviderNotReady(RuntimeError):
    """Raised when the model cannot be reached. Carries the setup hint."""


def _aws_credentials_exist():
    """True if boto3 can resolve credentials from anywhere in its chain."""
    try:
        import boto3

        return boto3.Session().get_credentials() is not None
    except Exception:
        return False


def _env(name):
    """A setting from the environment, falling back to the Windows user environment.

    `setx` saves to the user environment, but a terminal that was already open -
    and every VS Code terminal until VS Code restarts - never sees it. Reading the
    registry as well means a key saved with setx works straight away, anywhere.
    """
    value = os.environ.get(name)
    if value or sys.platform != "win32":
        return value
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as reg:
            return winreg.QueryValueEx(reg, name)[0]
    except OSError:
        return None


def resolve_model(provider):
    """The model the agent will run: FILLIN_MODEL if set, else the provider default."""
    return _env("FILLIN_MODEL") or DEFAULT_MODEL.get(provider)


def resolve_provider():
    """Explicit choice wins; otherwise whichever credentials are present."""
    explicit = (_env("FILLIN_PROVIDER") or "").strip().lower()
    if explicit:
        return explicit
    if _aws_credentials_exist():
        return "bedrock"
    if _env("ANTHROPIC_API_KEY"):
        return "anthropic"
    if _env("GOOGLE_API_KEY") or _env("GEMINI_API_KEY"):
        return "gemini"
    return ""


def build_model(provider=None):
    provider = provider or resolve_provider()
    if not provider:
        raise ProviderNotReady(SETUP_HINT)

    model_id = resolve_model(provider)
    if not model_id:
        raise ProviderNotReady(
            f"Unknown FILLIN_PROVIDER '{provider}'. Use 'gemini', 'bedrock' or 'anthropic'."
        )

    if provider == "anthropic":
        if not _env("ANTHROPIC_API_KEY"):
            raise ProviderNotReady("FILLIN_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set.")
        try:
            from strands.models.anthropic import AnthropicModel
        except ImportError as exc:
            raise ProviderNotReady(
                'The Anthropic provider needs: pip install "strands-agents[anthropic]"'
            ) from exc
        return AnthropicModel(
            client_args={"api_key": _env("ANTHROPIC_API_KEY")},
            model_id=model_id,
            max_tokens=2000,
        )

    if provider == "gemini":
        # Same precedence as Google's own SDKs: GOOGLE_API_KEY wins if both exist.
        key = _env("GOOGLE_API_KEY") or _env("GEMINI_API_KEY")
        if not key:
            raise ProviderNotReady(
                "FILLIN_PROVIDER=gemini but neither GEMINI_API_KEY nor GOOGLE_API_KEY is set."
            )
        try:
            from strands.models.gemini import GeminiModel
        except ImportError as exc:
            raise ProviderNotReady(
                'The Gemini provider needs: pip install "strands-agents[gemini]"'
            ) from exc
        return GeminiModel(client_args={"api_key": key}, model_id=model_id)

    if provider == "bedrock":
        from strands.models import BedrockModel

        return BedrockModel(model_id=model_id)

    raise ProviderNotReady(f"Unknown FILLIN_PROVIDER '{provider}'. Use 'gemini', 'bedrock' or 'anthropic'.")


# Credential failures surface deep inside botocore or httpx, as a wall of
# traceback. Recognise them and say the useful thing instead.
_CREDENTIAL_MARKERS = (
    "InvalidClientTokenId",
    "UnrecognizedClientException",
    "ExpiredToken",
    "AccessDeniedException",
    "NoCredentialsError",
    "could not be found",
    "authentication_error",
    "invalid x-api-key",
    "AccessDeniedError",
    "API_KEY_INVALID",
    "API key not valid",
    "UNAUTHENTICATED",
    "PERMISSION_DENIED",
)


def _as_provider_error(exc):
    """Return a ProviderNotReady if exc looks like a credentials problem."""
    text = f"{type(exc).__name__}: {exc}"
    if any(marker.lower() in text.lower() for marker in _CREDENTIAL_MARKERS):
        return ProviderNotReady(f"{text}\n\n{SETUP_HINT}")
    return None


SYSTEM_PROMPT = f"""You are Fill In, the agent that quietly backfills cancelled
volunteer shifts for a community kitchen. A coordinator used to do this by
phoning down a list. You do it instead, and you only involve them when a human
judgement is genuinely required.

For the shift you are given, take ONE step and then stop:

1. Call get_shift and check_replies to see where things stand.
2. If someone accepted, call confirm_and_book. You are done.
3. If nobody has been asked yet, or the last person declined or timed out, call
   rank_candidates and send_ask to the single best remaining candidate. Ask one
   person at a time - a queue of people all told "we need you" is worse than the
   problem you are solving.
4. If someone is still inside their {ASK_TIMEOUT_MINUTES} minute window, do
   nothing. Say you are waiting and stop.

Escalate to the coordinator with escalate_to_human when:
- {MAX_ASKS_PER_SHIFT} people have been asked and nobody accepted
- the shift starts within {URGENT_WINDOW_HOURS} hours
- no qualified candidate exists at all
- anything about the situation is ambiguous

escalate_to_human is your only way to reach a person. There is no other channel,
so do not describe problems in your reply and assume someone reads them.

When you write a message in send_ask, write it to that specific person about
that specific shift. Mention the role, and the day and time exactly as
get_shift's `when` gives them. Keep it to two sentences,
warm and easy to decline - these are volunteers, not staff. Never imply they are
letting anyone down.

Fairness is part of the job. rank_candidates already accounts for who has been
carrying the load; trust its order and do not reach past it for someone you
"know" will say yes. Burning out reliable volunteers is a failure, not a win."""


def build_agent(model=None):
    return Agent(
        model=model or build_model(),
        system_prompt=SYSTEM_PROMPT,
        tools=TOOLS,
    )


def handle_shift(shift_id, model=None):
    """Move one open shift forward by a single step.

    A fresh Agent per shift on purpose: one shift's conversation must not leak
    into the next one's decision.
    """
    agent = build_agent(model=model)
    result = agent(
        f"Shift {shift_id} needs cover. Check the current state and take the "
        f"next appropriate step."
    )
    return str(result)


def tick():
    """One wake-up. Called by the scheduler, not by a user."""
    open_shifts = query("SELECT id FROM shifts WHERE status = 'open'")
    if not open_shifts:
        return {"provider": resolve_provider(), "open_shifts": 0, "handled": []}

    provider = resolve_provider()
    model = build_model(provider)  # raises ProviderNotReady before touching the DB

    handled = []
    for row in open_shifts:
        sid = row["id"]
        log_event("tick", f"Agent woke up for shift {sid}.", sid)
        try:
            handled.append({"shift_id": sid, "outcome": handle_shift(sid, model=model)})
        except Exception as exc:
            provider_error = _as_provider_error(exc)
            if provider_error:
                raise provider_error from exc
            # One shift failing is not a reason to abandon the others. Doing
            # nothing for this one is the safe move.
            handled.append({"shift_id": sid, "error": f"{type(exc).__name__}: {exc}"})

    return {"provider": provider, "open_shifts": len(open_shifts), "handled": handled}
