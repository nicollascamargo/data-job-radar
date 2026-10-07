"""SQLite store: remembers every job seen so nothing is sent twice.

It also keeps the extracted skills of every data job collected, which later
feeds an analysis of what the market asks for.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import Evaluation, Job, norm

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    key          TEXT PRIMARY KEY,
    title        TEXT,
    company      TEXT,
    location     TEXT,
    site         TEXT,
    url          TEXT,
    area         TEXT,
    level        TEXT,
    modality     TEXT,
    score        INTEGER,
    matched      INTEGER,
    skills       TEXT,     -- every skill the job asks for
    missing      TEXT,     -- the ones not in my CV
    skill_match  INTEGER,  -- % of the job's skills I have
    date_posted  TEXT,
    first_seen   TEXT,
    last_seen    TEXT,
    notified_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_last_seen ON jobs(last_seen);
"""


def job_key(job: Job) -> str:
    """Same title at the same company = same job, even when found on two sites."""
    raw = f"{norm(job.title)}|{norm(job.company)}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str | Path = "data/jobs.db"):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.executescript(SCHEMA)

    def seen_recently(self, key: str, days: int, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        cutoff = (now - timedelta(days=days)).isoformat(timespec="seconds")
        row = self.conn.execute(
            "SELECT 1 FROM jobs WHERE key = ? AND last_seen >= ?", (key, cutoff)
        ).fetchone()
        return row is not None

    def touch(self, key: str, when: str | None = None) -> None:
        self.conn.execute("UPDATE jobs SET last_seen = ? WHERE key = ?", (when or now_utc(), key))

    def save(self, key: str, job: Job, ev: Evaluation, when: str | None = None) -> None:
        when = when or now_utc()
        self.conn.execute(
            """
            INSERT INTO jobs (key, title, company, location, site, url, area, level, modality,
                              score, matched, skills, missing, skill_match, date_posted,
                              first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                title=excluded.title, company=excluded.company, location=excluded.location,
                site=excluded.site, url=excluded.url, area=excluded.area, level=excluded.level,
                modality=excluded.modality, score=excluded.score, matched=excluded.matched,
                skills=excluded.skills, missing=excluded.missing,
                skill_match=excluded.skill_match, date_posted=excluded.date_posted,
                last_seen=excluded.last_seen, notified_at=NULL
            """,
            (key, job.title, job.company, job.location, job.site, job.url, ev.area, ev.level,
             ev.modality, ev.score, int(ev.matched), ",".join(ev.skills + ev.missing),
             ",".join(ev.missing), ev.skill_match, job.date_posted, when, when),
        )

    def mark_notified(self, keys: list[str], when: str | None = None) -> None:
        when = when or now_utc()
        self.conn.executemany(
            "UPDATE jobs SET notified_at = ? WHERE key = ?", [(when, k) for k in keys]
        )

    def commit(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        self.conn.commit()
        self.conn.close()
