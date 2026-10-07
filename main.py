"""Data Job Radar — entry point.

    python main.py                  # collect, match and send to Telegram
    python main.py --dry-run        # same, but print instead of sending
    python main.py --sample         # offline demo with tests/fixtures/sample_jobs.json
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import re
import sys
from pathlib import Path

from radar.collectors import CollectReport, collect
from radar.config import load_config
from radar.matcher import evaluate
from radar.models import Job
from radar.notifier import SITE_LABELS, build_messages, send_telegram
from radar.storage import Store, job_key

log = logging.getLogger("radar")
SAMPLE_FILE = Path(__file__).parent / "tests" / "fixtures" / "sample_jobs.json"


def load_sample(path: Path = SAMPLE_FILE) -> CollectReport:
    report = CollectReport()
    for item in json.loads(path.read_text(encoding="utf-8")):
        job = Job(**item)
        report.jobs.append(job)
        report.counts[job.site] += 1
        report.searches[job.site] = 1
    return report


def source_warnings(report: CollectReport) -> list[str]:
    warnings = []
    for site, failed in report.failures.items():
        name = SITE_LABELS.get(site, site)
        total = report.searches[site]
        if failed == total:
            warnings.append(f"{name} falhou em todas as buscas: {report.errors.get(site, '')[:100]}")
        else:
            warnings.append(f"{name} falhou em {failed} de {total} buscas")
    return warnings


def process(report: CollectReport, store: Store, config: dict):
    """Dedupes, evaluates and stores the jobs. Returns matches sorted by score."""
    matches = []
    for job in report.jobs:
        if not job.title or not job.url:
            continue
        key = job_key(job)
        if store.seen_recently(key, config["dedupe_days"]):
            store.touch(key)
            continue
        ev = evaluate(job, config)
        if not ev.area:  # not a data job: don't keep it
            continue
        store.save(key, job, ev)
        if ev.matched:
            matches.append((key, job, ev))
    matches.sort(key=lambda m: m[2].score, reverse=True)
    return matches


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Finds junior/intern data jobs and alerts on Telegram.")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--db", default="data/jobs.db")
    parser.add_argument("--dry-run", action="store_true", help="print instead of sending")
    parser.add_argument("--sample", action="store_true", help="use offline sample jobs")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = load_config(args.config)
    secrets = config["secrets"]
    dry_run = args.dry_run or not (secrets["telegram_token"] and secrets["telegram_chat_id"])
    if dry_run and not args.dry_run:
        log.warning("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set: printing instead of sending")

    report = load_sample() if args.sample else collect(config)
    log.info("collected %d jobs: %s", len(report.jobs), dict(report.counts))

    # The sample demo uses a throwaway database; a dry run reads the real one but saves nothing.
    store = Store(":memory:" if args.sample else args.db)
    matches = process(report, store, config)
    top = matches[: config["max_jobs_per_run"]]
    extra = len(matches) - len(top)
    warnings = source_warnings(report)
    log.info("%d new matching jobs (%d to notify, %d only stored)", len(matches), len(top), extra)

    total_failure = any(report.failures[s] == report.searches[s] for s in report.failures)
    should_send = top or config["notify_when_empty"] or total_failure
    messages = build_messages([(job, ev) for _, job, ev in top], extra, warnings) if should_send else []

    if dry_run:
        for text in messages:
            print(html.unescape(re.sub(r"<[^>]+>", "", text)), end="\n\n")
        store.conn.rollback()
        store.conn.close()
        return 0
    if messages:
        try:
            send_telegram(messages, secrets["telegram_token"], secrets["telegram_chat_id"])
        except Exception as exc:
            store.conn.rollback()  # nothing marked as seen, so the next run retries
            log.error("could not send to Telegram: %s", exc)
            return 1
    store.mark_notified([key for key, _, _ in top])
    store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
