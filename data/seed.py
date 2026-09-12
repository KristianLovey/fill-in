

import random
import sys
import os
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.db import init_db, execute, now, iso  # noqa: E402

random.seed(7)  # reproducible demos

NAMES = [
    "Ana Kovac", "Marko Juric", "Ivana Babic", "Petar Novak", "Lucija Maric",
    "Tomislav Horvat", "Sara Vukovic", "Filip Petrovic", "Maja Knezevic", "Luka Saric",
    "Dora Pavlovic", "Ivan Bozic", "Nina Radic", "Josip Matic", "Klara Vidovic",
    "Damir Lukic", "Ema Grgic", "Stjepan Blazevic", "Tea Simunovic", "Mislav Cindric",
    "Lana Perkovic", "Bruno Kolar", "Iva Zupan", "Antonio Rukavina", "Petra Mesic",
]

CERTS = ["food_safety", "first_aid", "driver"]

ROLES = [
    ("Kitchen line", ""),
    ("Meal prep", "food_safety"),
    ("Front desk", ""),
    ("Delivery run", "driver"),
    ("Warehouse sorting", ""),
]


def seed_volunteers():
    for i, name in enumerate(NAMES, start=1):
        slug = name.lower().replace(" ", ".")
        email = f"{slug}@example.org"

        # About half hold at least one certificate.
        certs = []
        if random.random() < 0.45:
            certs.append("food_safety")
        if random.random() < 0.30:
            certs.append("first_aid")
        if random.random() < 0.25:
            certs.append("driver")

        # Deliberately uneven load: a few people carry far too much.
        if i <= 4:
            recent_shifts = random.randint(6, 9)      # the burnout candidates
        elif i <= 10:
            recent_shifts = random.randint(2, 4)
        else:
            recent_shifts = random.randint(0, 2)      # barely used

        execute(
            """INSERT INTO volunteers
               (id, name, email, certs, shifts_last_30d, asks_last_30d, response_rate)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                i, name, email, ",".join(certs),
                recent_shifts,
                recent_shifts + random.randint(0, 3),
                round(random.uniform(0.25, 0.95), 2),
            ),
        )

        # Each volunteer declares 2-4 recurring weekly windows.
        for _ in range(random.randint(2, 4)):
            weekday = random.randint(0, 6)
            start = random.choice([7, 9, 12, 15, 17])
            execute(
                "INSERT INTO availability (volunteer_id, weekday, start_hour, end_hour) "
                "VALUES (?, ?, ?, ?)",
                (i, weekday, start, min(start + random.choice([4, 5, 6]), 23)),
            )


def seed_shifts():
    """A week of shifts starting tomorrow, all currently filled."""
    base = now().replace(hour=9, minute=0, second=0) + timedelta(days=1)
    shift_id = 1
    for day in range(7):
        for role, cert in random.sample(ROLES, 3):
            start = base + timedelta(days=day, hours=random.choice([0, 3, 6]))
            end = start + timedelta(hours=4)

            # Assign someone who actually holds the certificate.
            if cert:
                pool = [v for v in range(1, 26) if cert in _certs_of(v)]
            else:
                pool = list(range(1, 26))
            assigned = random.choice(pool) if pool else None

            execute(
                """INSERT INTO shifts
                   (id, role, location, starts_at, ends_at, required_cert, status, assigned_to)
                   VALUES (?, ?, ?, ?, ?, ?, 'filled', ?)""",
                (shift_id, role, "Community Kitchen, Main St", iso(start), iso(end), cert, assigned),
            )
            shift_id += 1


_certs_cache = {}


def _certs_of(vid):
    if vid not in _certs_cache:
        from agent.db import query
        row = query("SELECT certs FROM volunteers WHERE id = ?", (vid,))
        _certs_cache[vid] = row[0]["certs"].split(",") if row else []
    return _certs_cache[vid]


if __name__ == "__main__":
    init_db()
    seed_volunteers()
    seed_shifts()
    print("Seeded 25 volunteers and a week of shifts.")
    print("Cancel one with:  python -m agent.cli cancel <shift_id>")