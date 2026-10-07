"""Decides whether a job fits the profile and gives it a 0-100 score.

Rules, in order:
  1. The title must be a data role (analysis, engineering or science).
  2. The level must be internship or junior. Senior/mid-level titles are dropped;
     titles with no level are kept with a lower score unless the description asks
     for more years of experience than allowed.
  3. The job must be remote, or in/near one of the target cities.
  4. Score = level + area + share of the job's skills found in my CV + location,
     minus penalties.
"""

from __future__ import annotations

import re

from .models import Evaluation, Job, norm
from .skills import extract_skills

AREA_PATTERNS: dict[str, list[str]] = {
    "analise": [
        r"analista de dados", r"analise de dados", r"data analyst", r"data analytics",
        r"analista de bi\b", r"\bbi analyst", r"business intelligence",
        r"analista de (inteligencia|analytics)", r"analytics analyst",
    ],
    "engenharia": [
        r"engenheir[oa] de dados", r"engenharia de dados", r"data engineer",
        r"analytics engineer", r"\bdataops\b", r"desenvolvedor[a]? (de )?(etl|dados)",
    ],
    "ciencia": [
        r"cientista de dados", r"ciencia de dados", r"data scien", r"machine learning",
        r"\bml engineer", r"\bmlops\b", r"inteligencia artificial", r"\bai engineer",
    ],
}
AREA_LABELS = {"analise": "Análise de dados", "engenharia": "Engenharia de dados",
               "ciencia": "Ciência de dados", "geral": "Dados"}

GENERIC_DATA = re.compile(r"\b(dados|data|bi|analytics)\b")
NOT_DATA_ROLE = re.compile(
    r"entrada de dados|digitad|cadastr|data entry|data ?center|protecao de dados|"
    r"privacidade|\bdpo\b|cabeamento"
)

INTERN = re.compile(r"\bestagi|\bintern(ship)?\b|\bestudante\b")
JUNIOR = re.compile(
    r"\b(junior|jr|trainee)\b|\bentry[ -]level\b|(?<=\s)i(?=\s*($|[-|(/]))"
)
SENIOR = re.compile(
    r"\b(senior|sr|pleno|lead|lider|especialista|specialist|coordenador[a]?|coordinator|"
    r"gerente|manager|head|staff|principal|diretor[a]?|director|supervisor[a]?|"
    r"arquitet[oa]|architect|ii|iii|iv)\b|\bpl\b(?!/)"
)
LINKEDIN_LEVELS = {
    "internship": "estagio",
    "entry level": "junior",
    "mid-senior level": "senior",
    "director": "senior",
    "executive": "senior",
}

YEARS_PATTERNS = [
    re.compile(r"(\d{1,2})\s*\+?\s*anos?\s*(?:ou mais\s*)?de\s*experiencia"),
    re.compile(r"experiencia\s*(?:minima\s*|previa\s*|comprovada\s*)?de\s*(\d{1,2})\s*\+?\s*anos?"),
    re.compile(r"(\d{1,2})\s*\+?\s*years?\s*(?:of\s*)?(?:professional\s*|relevant\s*|work\s*|hands-on\s*)?experience"),
]

REMOTE_SHORT = re.compile(r"\b(remot[oa]|remote|home office|anywhere)\b")
REMOTE_IN_TEXT = re.compile(
    r"100% remot|totalmente remot|trabalho remoto|modelo remoto|home office|"
    r"full[ -]remote|fully remote|remote[ -]first"
)
HYBRID = re.compile(r"\b(hibrid[oa]|hybrid)\b")


def detect_area(title: str) -> str:
    for area, patterns in AREA_PATTERNS.items():
        if any(re.search(p, title) for p in patterns):
            return area
    return "geral" if GENERIC_DATA.search(title) else ""


def detect_level(title: str, job_level: str, description: str) -> tuple[str, str]:
    """Returns (level, how it was found)."""
    if INTERN.search(title):
        return "estagio", "title"
    if JUNIOR.search(title):
        return "junior", "title"
    if SENIOR.search(title):
        return "senior", "title"
    linkedin = LINKEDIN_LEVELS.get(job_level)
    if linkedin:
        return linkedin, "linkedin"
    if INTERN.search(description):
        return "estagio", "description"
    if re.search(r"\b(junior|jr)\b", description):
        return "junior", "description"
    return "nao informado", ""


def years_required(description: str) -> int | None:
    found = [int(n) for p in YEARS_PATTERNS for n in p.findall(description)]
    found = [n for n in found if 0 < n <= 15]
    return max(found) if found else None


def detect_modality(job: Job, title: str, location: str, description: str) -> str:
    if job.is_remote or REMOTE_SHORT.search(title) or REMOTE_SHORT.search(location) \
            or REMOTE_IN_TEXT.search(description):
        return "remoto"
    if HYBRID.search(title) or HYBRID.search(location) or HYBRID.search(description):
        return "hibrido"
    return "presencial"


def in_target_city(location: str, cities: list[str]) -> bool:
    first_part = location.split(",")[0].strip()
    return any(norm(city) in first_part for city in cities)


def compare_skills(job: Job, my_skills: list[str]) -> tuple[list[str], list[str], int | None, int]:
    """What the job asks for vs. what the CV has.

    Returns (have, missing, match %, score points out of 25). A job that names
    only one or two skills says little, so its points lean toward a neutral 10.
    """
    required = extract_skills(f"{job.title} {job.description}")
    if not required:
        return [], [], None, 10
    mine = set(my_skills)
    have = [s for s in required if s in mine]
    missing = [s for s in required if s not in mine]
    coverage = len(have) / len(required)
    confidence = min(1.0, len(required) / 3)
    points = round(25 * coverage * confidence + 10 * (1 - confidence))
    return have, missing, round(100 * coverage), points


def evaluate(job: Job, config: dict) -> Evaluation:
    title = norm(job.title)
    location = norm(job.location)
    description = norm(job.description)
    reasons: list[str] = []

    # 1. Data role?
    area = detect_area(title)
    if not area or NOT_DATA_ROLE.search(title):
        return Evaluation(False, 0, reasons=["not a data role"])

    # 2. Level
    level, level_source = detect_level(title, norm(job.job_level), description)
    if level == "senior":
        return Evaluation(False, 0, area=area, level=level, reasons=["level above junior"])
    if level == "nao informado" and not config["accept_unspecified_level"]:
        return Evaluation(False, 0, area=area, level=level, reasons=["level not stated"])
    if level in {"estagio", "junior"} and level not in config["levels"]:
        return Evaluation(False, 0, area=area, level=level, reasons=["level not wanted"])

    years = years_required(description)
    too_experienced = years is not None and years > config["max_years_experience"]
    if too_experienced and level_source != "title":
        return Evaluation(False, 0, area=area, level=level,
                          reasons=[f"asks for {years}+ years of experience"])

    # 3. Location / modality
    modality = detect_modality(job, title, location, description)
    city_match = in_target_city(location, config["cities"])
    from_city_search = job.origin not in ("", "remote")
    if modality != "remoto" and not city_match and not from_city_search:
        return Evaluation(False, 0, area=area, level=level, modality=modality,
                          reasons=["not remote and not in a target city"])

    # 4. Score
    score = {"title": 35, "linkedin": 30, "description": 20}.get(level_source, 10)
    score += 12 if area == "geral" else 25
    have, missing, skill_match, skill_points = compare_skills(job, config["my_skills"])
    score += skill_points
    if skill_match is not None and skill_match < config["min_skill_match"]:
        return Evaluation(False, 0, area=area, level=level, modality=modality, skills=have,
                          missing=missing, skill_match=skill_match,
                          reasons=[f"only {skill_match}% of the skills asked"])
    score += 10 if (modality == "remoto" or city_match) else 5
    if too_experienced:
        score -= 20
        reasons.append(f"asks for {years}+ years")
    score = max(0, min(100, score))

    return Evaluation(
        matched=score >= config["min_score"],
        score=score,
        area=area,
        level=level,
        modality=modality,
        skills=have,
        missing=missing,
        skill_match=skill_match,
        reasons=reasons if score >= config["min_score"] else reasons + ["score below minimum"],
    )
