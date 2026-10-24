from datetime import datetime, timedelta, timezone

from main import load_sample, process
from radar.config import load_config
from radar.models import Evaluation, Job
from radar.notifier import TELEGRAM_LIMIT, build_messages
from radar.storage import Store, job_key


def test_sample_run_finds_expected_jobs():
    config = load_config("config.yaml")
    matches = process(load_sample(), Store(":memory:"), config)
    titles = [job.title for _, job, _ in matches]
    assert len(titles) == 6
    assert "Analista de Dados Sênior" not in titles
    assert "Engenheiro de Dados Pleno" not in titles
    assert "Cientista de Dados Jr" not in titles          # on-site in Ribeirão Preto
    assert "Engenheiro de Dados Jr" not in titles         # asks mostly for skills not in the CV
    assert titles.count("Analista de Dados Júnior") == 1  # same job on two sites
    scores = [ev.score for _, _, ev in matches]
    assert scores == sorted(scores, reverse=True)


def test_second_run_sends_nothing_new():
    config = load_config("config.yaml")
    store = Store(":memory:")
    assert process(load_sample(), store, config)
    assert process(load_sample(), store, config) == []


def test_job_comes_back_after_dedupe_window():
    store = Store(":memory:")
    j = Job(site="indeed", title="Analista de Dados Jr", company="ACME", location="Sorocaba", url="u")
    key = job_key(j)
    old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat(timespec="seconds")
    store.save(key, j, Evaluation(True, 80, area="analise"), when=old)
    assert store.seen_recently(key, days=30) is False
    assert store.seen_recently(key, days=60) is True


def test_long_alerts_are_split_for_telegram():
    j = Job(site="linkedin", title="Analista de Dados Jr " + "x" * 300, company="ACME",
            location="Sorocaba", url="https://example.com")
    ev = Evaluation(True, 80, area="analise", level="junior", modality="hibrido")
    messages = build_messages([(j, ev)] * 30, extra=5, warnings=["LinkedIn falhou em 1 de 15 buscas"])
    assert len(messages) > 1
    assert all(len(m) <= TELEGRAM_LIMIT for m in messages)
    assert "LinkedIn falhou" in messages[-1]


def test_matched_jobs_keep_their_text_for_cv_tailor():
    from radar.storage import unpack
    store = Store(":memory:")
    j = Job(site="gupy", title="Analista de Dados Jr", company="ACME", location="Sorocaba", url="u",
            description="Requisitos: Python e SQL", deadline="2026-11-20")
    store.save(job_key(j), j, Evaluation(True, 80, area="analise"))
    other = Job(site="gupy", title="Analista de Dados Sênior", company="ACME", location="Sorocaba", url="v",
                description="texto")
    store.save(job_key(other), other, Evaluation(False, 0, area="analise"))
    rows = dict(store.conn.execute("SELECT title, description FROM jobs").fetchall())
    assert unpack(rows["Analista de Dados Jr"]) == "Requisitos: Python e SQL"
    assert rows["Analista de Dados Sênior"] is None              # only matched jobs keep the text
    later = datetime.now(timezone.utc) + timedelta(days=61)
    assert store.forget_old_texts(60, now=later) == 1


def test_old_databases_get_the_new_columns(tmp_path):
    import sqlite3
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE jobs (key TEXT PRIMARY KEY, title TEXT, company TEXT, location TEXT, site TEXT, "
                 "url TEXT, area TEXT, level TEXT, modality TEXT, score INTEGER, matched INTEGER, skills TEXT, "
                 "missing TEXT, skill_match INTEGER, date_posted TEXT, first_seen TEXT, last_seen TEXT, notified_at TEXT)")
    conn.commit()
    conn.close()
    store = Store(path)
    assert {"description", "deadline"} <= {r[1] for r in store.conn.execute("PRAGMA table_info(jobs)")}


def test_alert_says_when_it_was_posted_and_until_when_to_apply():
    from datetime import date
    from radar.notifier import format_job
    j = Job(site="gupy", title="Estágio em Dados", company="NCS", location="São Paulo, SP", url="https://x",
            date_posted="2026-10-23", deadline="2026-10-26")
    ev = Evaluation(True, 89, area="analise", level="estagio", modality="hibrido", skills=["python"], skill_match=80)
    text = format_job(j, ev, today=date(2026, 10, 24))
    assert "publicada ontem" in text and "inscrições até 26/10 (faltam 2 dias)" in text and "Gupy" in text
