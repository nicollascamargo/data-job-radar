"""Collects job postings from LinkedIn, Indeed and Glassdoor (via JobSpy), Gupy and Adzuna."""

from __future__ import annotations

import logging
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import requests

from .models import Job, clean, norm

log = logging.getLogger(__name__)

ADZUNA_URL = "https://api.adzuna.com/v1/api/jobs/br/search/{page}"
# The search behind portal.gupy.io: most Brazilian companies post their jobs on Gupy,
# often only there, with the full text and the application deadline.
GUPY_URL = "https://portal.gupy.io/api/job-search/jobs"
GUPY_PAGE = 100
GUPY_MAX_PAGES = 5
GUPY_LEVELS = {"vacancy_type_internship": "internship", "vacancy_type_trainee": "entry level"}
# not an opening I can apply to as a student: talent pools, apprentice programs, freelancing
GUPY_SKIP = {"vacancy_type_talent_pool", "vacancy_type_apprentice", "vacancy_type_freelancer",
             "vacancy_type_autonomous", "vacancy_type_lecturer"}
STATES = {
    "acre": "AC", "alagoas": "AL", "amapa": "AP", "amazonas": "AM", "bahia": "BA", "ceara": "CE",
    "distrito federal": "DF", "espirito santo": "ES", "goias": "GO", "maranhao": "MA", "mato grosso": "MT",
    "mato grosso do sul": "MS", "minas gerais": "MG", "para": "PA", "paraiba": "PB", "parana": "PR",
    "pernambuco": "PE", "piaui": "PI", "rio de janeiro": "RJ", "rio grande do norte": "RN",
    "rio grande do sul": "RS", "rondonia": "RO", "roraima": "RR", "santa catarina": "SC",
    "sao paulo": "SP", "sergipe": "SE", "tocantins": "TO",
}

# JobSpy logs scraping errors and returns an empty table instead of raising,
# so the radar listens to its loggers to tell "no jobs today" from "site blocked us".
JOBSPY_LOGGERS = {"indeed": "Indeed", "linkedin": "LinkedIn", "glassdoor": "Glassdoor",
                  "google": "Google", "zip_recruiter": "ZipRecruiter"}


class _ErrorCatcher(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.ERROR)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


@dataclass
class CollectReport:
    jobs: list[Job] = field(default_factory=list)
    counts: Counter = field(default_factory=Counter)        # jobs per site
    searches: Counter = field(default_factory=Counter)      # searches tried per site
    failures: Counter = field(default_factory=Counter)      # searches that failed per site
    errors: dict[str, str] = field(default_factory=dict)    # site -> last error


def first_phrase(query: str) -> str:
    """'"analista de dados" OR "data analyst"' -> 'analista de dados'."""
    quoted = re.findall(r'"([^"]+)"', query)
    return quoted[0] if quoted else query


def build_searches(config: dict) -> list[dict]:
    """Every (area, place) pair the radar should search."""
    places = [{"location": loc, "origin": loc, "is_remote": False} for loc in config["locations"]]
    if config.get("search_remote"):
        places.append({"location": config["remote_location"], "origin": "remote", "is_remote": True})
    return [
        {"area": area, "query": query, **place}
        for area, query in config["queries"].items()
        for place in places
    ]


def _bool(value) -> bool | None:
    if isinstance(value, bool):
        return value
    text = clean(value).lower()
    if text in {"true", "1"}:
        return True
    if text in {"false", "0"}:
        return False
    return None


def scrape_jobspy(config: dict, report: CollectReport) -> None:
    from jobspy import scrape_jobs  # imported lazily so tests don't need network libs

    for search in build_searches(config):
        for site in config["sites"]:
            term = first_phrase(search["query"]) if site == "glassdoor" else search["query"]
            report.searches[site] += 1
            catcher = _ErrorCatcher()
            site_logger = logging.getLogger(f"JobSpy:{JOBSPY_LOGGERS.get(site, site)}")
            site_logger.addHandler(catcher)
            try:
                df = scrape_jobs(
                    site_name=[site],
                    search_term=term,
                    location=search["location"],
                    distance=config["distance_miles"],
                    is_remote=search["is_remote"],
                    results_wanted=config["results_per_search"],
                    hours_old=config["hours_old"],
                    country_indeed="brazil",
                    linkedin_fetch_description=config["linkedin_fetch_description"],
                    proxies=config["proxies"] or None,
                    verbose=0,
                )
            except Exception as exc:  # one broken site must not stop the run
                catcher.messages.append(f"{type(exc).__name__}: {exc}")
                df = None
            finally:
                site_logger.removeHandler(catcher)

            if catcher.messages and (df is None or df.empty):
                report.failures[site] += 1
                report.errors[site] = catcher.messages[-1][:160]
                log.warning("%s failed for %s / %s", site, search["area"], search["origin"])
                time.sleep(config["pause_seconds"])
                continue

            for row in df.to_dict("records"):
                report.jobs.append(
                    Job(
                        site=clean(row.get("site")) or site,
                        title=clean(row.get("title")),
                        company=clean(row.get("company")),
                        location=clean(row.get("location")),
                        url=clean(row.get("job_url")),
                        description=clean(row.get("description")),
                        is_remote=_bool(row.get("is_remote")),
                        job_level=clean(row.get("job_level")),
                        date_posted=clean(row.get("date_posted")),
                        origin=search["origin"],
                        query_area=search["area"],
                    )
                )
            report.counts[site] += len(df)
            log.info("%-9s %-11s %-18s -> %d", site, search["area"], search["origin"], len(df))
            time.sleep(config["pause_seconds"])


def scrape_adzuna(config: dict, report: CollectReport) -> None:
    secrets = config["secrets"]
    if not (config.get("adzuna") and secrets["adzuna_app_id"] and secrets["adzuna_app_key"]):
        return

    days = max(1, round(config["hours_old"] / 24))
    places = [(loc.split(",")[0], loc) for loc in config["locations"]]
    if config.get("search_remote"):
        places.append(("", "remote"))  # nationwide; the matcher keeps only remote ones

    for area, query in config["queries"].items():
        phrases = re.findall(r'"([^"]+)"', query) or [query]
        for phrase in phrases:
            for where, origin in places:
                params = {
                    "app_id": secrets["adzuna_app_id"],
                    "app_key": secrets["adzuna_app_key"],
                    "what_phrase": phrase,
                    "max_days_old": days,
                    "results_per_page": min(50, config["results_per_search"]),
                    "content-type": "application/json",
                }
                if where:
                    params["where"] = where
                    params["distance"] = round(config["distance_miles"] * 1.6)
                report.searches["adzuna"] += 1
                try:
                    resp = requests.get(ADZUNA_URL.format(page=1), params=params, timeout=30)
                    resp.raise_for_status()
                    results = resp.json().get("results", [])
                except Exception as exc:
                    report.failures["adzuna"] += 1
                    report.errors["adzuna"] = f"{type(exc).__name__}: {exc}"[:200]
                    log.warning("adzuna failed for %s / %s: %s", phrase, origin, exc)
                    continue

                for item in results:
                    report.jobs.append(
                        Job(
                            site="adzuna",
                            title=clean(item.get("title")),
                            company=clean((item.get("company") or {}).get("display_name")),
                            location=clean((item.get("location") or {}).get("display_name")),
                            url=clean(item.get("redirect_url")),
                            description=clean(item.get("description")),
                            date_posted=clean(item.get("created"))[:10],
                            origin=origin,
                            query_area=area,
                        )
                    )
                report.counts["adzuna"] += len(results)
                time.sleep(1)


def gupy_terms(config: dict) -> list[str]:
    """Gupy searches job titles, one phrase at a time: the Portuguese phrases of the queries
    (English titles are rare there) plus gupy_extra_terms."""
    phrases = []
    for query in config["queries"].values():
        found = re.findall(r'"([^"]+)"', query) or [query]
        phrases += [p for p in found if not re.search(r"\b(data|analyst|engineer|scientist)\b", p.lower())]
    return list(dict.fromkeys(phrases + list(config.get("gupy_extra_terms", []))))


def _state_code(state: str) -> str:
    return STATES.get(norm(state), clean(state))


def gupy_job(item: dict) -> Job | None:
    if item.get("type") in GUPY_SKIP:
        return None
    workplace = clean(item.get("workplaceType"))
    city, state = clean(item.get("city")), _state_code(item.get("state") or "")
    location = ", ".join(p for p in (city, state) if p) + (", Brasil" if city or state else "")
    if workplace == "remote" and not city:
        location = "Remoto, Brasil"
    modality = {"remote": "remoto", "hybrid": "híbrido", "on-site": "presencial"}.get(workplace, "")
    return Job(
        site="gupy",
        title=re.sub(r"\s+", " ", clean(item.get("name"))),
        company=clean(item.get("careerPageName")),
        location=location,
        url=clean(item.get("jobUrl")).split("?")[0],
        # Gupy glues the post's sections together; the work model goes first so the matcher sees it
        description=(f"Modelo de trabalho: {modality}.\n" if modality else "") + clean(item.get("description")),
        is_remote=workplace == "remote",
        job_level=GUPY_LEVELS.get(item.get("type"), ""),
        date_posted=clean(item.get("publishedDate"))[:10],
        deadline=clean(item.get("applicationDeadline"))[:10],
        origin="",                       # nationwide search: the matcher checks the city
        query_area="",
    )


def scrape_gupy(config: dict, report: CollectReport, now: datetime | None = None) -> None:
    """Newest first, page by page, until the jobs are older than hours_old."""
    if not config.get("gupy"):
        return
    cutoff = ((now or datetime.now(timezone.utc)) - timedelta(hours=config["hours_old"])).isoformat()
    for term in gupy_terms(config):
        report.searches["gupy"] += 1
        found = 0
        try:
            for page in range(GUPY_MAX_PAGES):
                resp = requests.get(GUPY_URL, params={"jobName": term, "limit": GUPY_PAGE,
                                                      "offset": page * GUPY_PAGE},
                                    headers={"User-Agent": "Mozilla/5.0 (data-job-radar)"}, timeout=30)
                resp.raise_for_status()
                items = resp.json().get("data", [])
                fresh = [i for i in items if clean(i.get("publishedDate")) >= cutoff]
                for item in fresh:
                    job = gupy_job(item)
                    if job and job.title and job.url:
                        report.jobs.append(job)
                        found += 1
                if len(fresh) < len(items) or len(items) < GUPY_PAGE:
                    break
                time.sleep(1)
        except Exception as exc:
            report.failures["gupy"] += 1
            report.errors["gupy"] = f"{type(exc).__name__}: {exc}"[:200]
            log.warning("gupy failed for %s: %s", term, exc)
            continue
        report.counts["gupy"] += found
        log.info("gupy      %-30s -> %d", term, found)
        time.sleep(1)


def collect(config: dict) -> CollectReport:
    report = CollectReport()
    scrape_jobspy(config, report)
    scrape_gupy(config, report)
    scrape_adzuna(config, report)
    return report
