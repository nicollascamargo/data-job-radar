import pandas as pd
import pytest

import jobspy
from radar import collectors
from radar.config import load_config


@pytest.fixture
def config():
    cfg = load_config("config.yaml")
    cfg["pause_seconds"] = 0
    cfg["adzuna"] = False
    cfg["gupy"] = False
    return cfg


def test_builds_one_search_per_area_and_place(config):
    searches = collectors.build_searches(config)
    assert len(searches) == 5 * 5  # 5 areas x (4 cities + remote)
    remote = [s for s in searches if s["origin"] == "remote"]
    assert all(s["is_remote"] and s["location"] == "Brasil" for s in remote)


def test_first_phrase_for_sites_without_boolean_search():
    assert collectors.first_phrase('"analista de dados" OR "data analyst"') == "analista de dados"
    assert collectors.first_phrase("data analyst") == "data analyst"


def test_one_failing_site_does_not_stop_the_others(config, monkeypatch):
    calls = []

    def fake_scrape_jobs(site_name, search_term, location, **kwargs):
        calls.append((site_name[0], search_term))
        assert kwargs["country_indeed"] == "brazil"
        if site_name[0] == "linkedin":
            raise RuntimeError("429 Too Many Requests")
        return pd.DataFrame([{
            "site": site_name[0], "title": "Analista de Dados Jr", "company": "ACME",
            "location": location, "job_url": "https://example.com", "description": float("nan"),
            "is_remote": False, "job_level": None, "date_posted": "2026-10-07",
        }])

    monkeypatch.setattr(jobspy, "scrape_jobs", fake_scrape_jobs)
    report = collectors.collect(config)

    assert len(calls) == 25 * 3
    assert report.failures["linkedin"] == report.searches["linkedin"] == 25
    assert report.counts["indeed"] == 25 and report.counts["glassdoor"] == 25
    assert all(j.description == "" for j in report.jobs)  # NaN cleaned
    glassdoor_terms = {term for site, term in calls if site == "glassdoor"}
    assert '"' not in "".join(glassdoor_terms)


def test_errors_logged_by_jobspy_count_as_failures(config, monkeypatch):
    """JobSpy logs errors and returns an empty table instead of raising."""
    import logging

    def fake_scrape_jobs(site_name, **kwargs):
        if site_name[0] == "glassdoor":
            logging.getLogger("JobSpy:Glassdoor").error("Glassdoor response status code 403")
        return pd.DataFrame()

    monkeypatch.setattr(jobspy, "scrape_jobs", fake_scrape_jobs)
    report = collectors.collect(config)

    assert report.failures["glassdoor"] == 25
    assert report.failures["indeed"] == 0          # empty but no error: just no jobs today
    assert "403" in report.errors["glassdoor"]


GUPY_PAGE = {"data": [
    {"name": "Estágio em Análise de Dados", "careerPageName": "NCS", "type": "vacancy_type_internship",
     "workplaceType": "hybrid", "city": "São Paulo", "state": "São Paulo", "publishedDate": "2026-10-23T21:09:40.403Z",
     "applicationDeadline": "2026-11-20T00:00:00.000Z", "description": "Requisitos: Python e SQL.",
     "jobUrl": "https://ncs.gupy.io/job/abc?jobBoardSource=gupy_portal"},
    {"name": "Banco de Talentos Dados", "careerPageName": "X", "type": "vacancy_type_talent_pool",
     "workplaceType": "remote", "publishedDate": "2026-10-23T10:00:00Z", "description": "", "jobUrl": "https://x"},
    {"name": "Analista de Dados", "careerPageName": "Old", "type": "vacancy_type_effective",
     "workplaceType": "remote", "publishedDate": "2026-10-01T10:00:00Z", "description": "", "jobUrl": "https://old"},
]}


def test_gupy_brings_fresh_openings_with_text_and_deadline(config, monkeypatch):
    from datetime import datetime, timezone
    calls = []

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return GUPY_PAGE

    def fake_get(url, params, headers, timeout):
        calls.append(params["jobName"])
        return Resp()

    monkeypatch.setattr(collectors.requests, "get", fake_get)
    config["gupy"] = True
    config["gupy_extra_terms"] = ["estágio dados"]
    report = collectors.CollectReport()
    collectors.scrape_gupy(config, report, now=datetime(2026, 10, 24, 12, tzinfo=timezone.utc))

    assert "analista de dados" in calls and "estágio dados" in calls and "data analyst" not in calls
    jobs = {j.company: j for j in report.jobs}
    assert set(jobs) == {"NCS"}                              # talent pool and old job left out
    ncs = jobs["NCS"]
    assert ncs.location == "São Paulo, SP, Brasil" and ncs.job_level == "internship"
    assert ncs.deadline == "2026-11-20" and ncs.url == "https://ncs.gupy.io/job/abc"
    assert ncs.description.startswith("Modelo de trabalho: híbrido.") and ncs.origin == ""
