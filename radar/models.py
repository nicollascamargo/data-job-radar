"""Shared data structures and text helpers."""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field


def clean(value) -> str:
    """Turns None/NaN/anything into a stripped string."""
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()


def norm(text) -> str:
    """Lowercase, no accents, no gender markers, single spaces: 'Hortolândia, SP' -> 'hortolandia, sp'."""
    text = unicodedata.normalize("NFKD", clean(text))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"\((?:a|o|as|os|e)\)", "", text)  # "engenheiro(a)" -> "engenheiro"
    return re.sub(r"\s+", " ", text).strip()


@dataclass
class Job:
    site: str
    title: str
    company: str
    location: str
    url: str
    description: str = ""
    is_remote: bool | None = None
    job_level: str = ""          # LinkedIn seniority label, when available
    date_posted: str = ""
    origin: str = ""             # the city searched, or "remote"
    query_area: str = ""         # analise / engenharia / ciencia


@dataclass
class Evaluation:
    matched: bool
    score: int
    area: str = ""
    level: str = ""              # estagio / junior / nao informado
    modality: str = ""           # remoto / hibrido / presencial
    skills: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)   # why it was rejected
