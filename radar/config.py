"""Loads config.yaml and secrets from environment variables."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

DEFAULTS: dict[str, Any] = {
    "queries": {},
    "locations": [],
    "distance_miles": 25,
    "search_remote": True,
    "remote_location": "Brasil",
    "sites": ["indeed", "linkedin", "glassdoor"],
    "adzuna": True,
    "hours_old": 24,
    "results_per_search": 30,
    "pause_seconds": 4,
    "linkedin_fetch_description": True,
    "proxies": [],
    "levels": ["estagio", "junior"],
    "accept_unspecified_level": True,
    "max_years_experience": 2,
    "cities": [],
    "my_skills": [],
    "min_score": 45,
    "max_jobs_per_run": 20,
    "dedupe_days": 30,
    "notify_when_empty": False,
}


def load_config(path: str | Path = "config.yaml") -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        user = yaml.safe_load(f) or {}
    config = {**DEFAULTS, **user}
    config["secrets"] = {
        "telegram_token": os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", "").strip(),
        "adzuna_app_id": os.getenv("ADZUNA_APP_ID", "").strip(),
        "adzuna_app_key": os.getenv("ADZUNA_APP_KEY", "").strip(),
    }
    return config
