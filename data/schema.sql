-- Fill In - database schema
-- Everything the agent knows lives here. The dashboard reads the same tables.

DROP TABLE IF EXISTS events;
DROP TABLE IF EXISTS escalations;
DROP TABLE IF EXISTS asks;
DROP TABLE IF EXISTS availability;
DROP TABLE IF EXISTS shifts;
DROP TABLE IF EXISTS volunteers;

CREATE TABLE volunteers (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    email           TEXT NOT NULL,
    certs           TEXT NOT NULL DEFAULT '',   -- comma separated, e.g. "food_safety,first_aid"
    shifts_last_30d INTEGER NOT NULL DEFAULT 0, -- fairness signal: recent load
    asks_last_30d   INTEGER NOT NULL DEFAULT 0, -- fatigue signal: how often we bothered them
    response_rate   REAL    NOT NULL DEFAULT 0.5
);

-- Weekly recurring availability. weekday: 0 = Monday ... 6 = Sunday
CREATE TABLE availability (
    volunteer_id INTEGER NOT NULL REFERENCES volunteers(id),
    weekday      INTEGER NOT NULL,
    start_hour   INTEGER NOT NULL,
    end_hour     INTEGER NOT NULL
);

CREATE TABLE shifts (
    id            INTEGER PRIMARY KEY,
    role          TEXT NOT NULL,               -- e.g. "Kitchen line"
    location      TEXT NOT NULL,
    starts_at     TEXT NOT NULL,               -- ISO 8601
    ends_at       TEXT NOT NULL,
    required_cert TEXT NOT NULL DEFAULT '',    -- '' = no certificate needed
    status        TEXT NOT NULL DEFAULT 'filled',  -- filled | open | escalated
    assigned_to   INTEGER REFERENCES volunteers(id)
);

-- One row per person the agent asked. This is the state of the backfill loop.
CREATE TABLE asks (
    id           INTEGER PRIMARY KEY,
    shift_id     INTEGER NOT NULL REFERENCES shifts(id),
    volunteer_id INTEGER NOT NULL REFERENCES volunteers(id),
    sent_at      TEXT NOT NULL,
    expires_at   TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending'  -- pending | accepted | declined | timeout | superseded
);

CREATE TABLE escalations (
    id         INTEGER PRIMARY KEY,
    shift_id   INTEGER NOT NULL REFERENCES shifts(id),
    reason     TEXT NOT NULL,
    detail     TEXT NOT NULL,
    created_at TEXT NOT NULL,
    resolved   INTEGER NOT NULL DEFAULT 0
);

-- Audit trail. Every autonomous action is written here, which is what the
-- dashboard shows in the "handled without you" column.
CREATE TABLE events (
    id       INTEGER PRIMARY KEY,
    ts       TEXT NOT NULL,
    shift_id INTEGER,
    kind     TEXT NOT NULL,   -- asked | accepted | declined | timeout | filled | escalated | notified
    detail   TEXT NOT NULL
);