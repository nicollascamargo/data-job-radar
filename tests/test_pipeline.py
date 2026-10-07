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
