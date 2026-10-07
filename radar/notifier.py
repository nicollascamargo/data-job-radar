"""Formats the matched jobs and sends them through a Telegram bot."""

from __future__ import annotations

import html
import logging

import requests

from .matcher import AREA_LABELS
from .models import Evaluation, Job

log = logging.getLogger(__name__)

TELEGRAM_LIMIT = 4000  # Telegram allows 4096 characters per message
LEVEL_LABELS = {"estagio": "Estágio", "junior": "Júnior", "nao informado": "Nível não informado"}
MODALITY_LABELS = {"remoto": "Remoto", "hibrido": "Híbrido", "presencial": "Presencial"}
SITE_LABELS = {"linkedin": "LinkedIn", "indeed": "Indeed", "glassdoor": "Glassdoor", "adzuna": "Adzuna"}


def format_job(job: Job, ev: Evaluation) -> str:
    e = html.escape
    place = "Remoto" if ev.modality == "remoto" else f"{job.location or job.origin} · {MODALITY_LABELS[ev.modality]}"
    lines = [
        f"<b>{e(job.title)}</b>",
        f"🏢 {e(job.company or 'Empresa não informada')}",
        f"📍 {e(place)}",
        f"🎯 {LEVEL_LABELS.get(ev.level, ev.level)} · {AREA_LABELS.get(ev.area, ev.area)} · {ev.score}/100",
    ]
    if ev.skill_match is not None:
        lines.append(f"🧩 Você tem {ev.skill_match}% das skills pedidas")
        if ev.skills:
            lines.append(f"✅ {e(', '.join(ev.skills))}")
        if ev.missing:
            lines.append(f"📚 Falta: {e(', '.join(ev.missing))}")
    else:
        lines.append("🧩 Vaga sem lista de skills — vale abrir e conferir")
    lines.append(f'🔗 <a href="{e(job.url, quote=True)}">Ver no {SITE_LABELS.get(job.site, job.site)}</a>')
    return "\n".join(lines)


def build_messages(matches: list[tuple[Job, Evaluation]], extra: int,
                   warnings: list[str]) -> list[str]:
    """Splits the alert into Telegram-sized messages."""
    if matches:
        header = f"🔎 <b>{len(matches) + extra} vaga(s) nova(s) de dados</b>"
    elif warnings:
        header = "⚠️ <b>Nenhuma vaga nova — e algumas fontes falharam</b>"
    else:
        header = "😴 <b>Nenhuma vaga nova hoje</b>"
    blocks = [format_job(job, ev) for job, ev in matches]
    footer = []
    if extra:
        footer.append(f"➕ {extra} vaga(s) com nota menor ficaram salvas no banco.")
    footer += [f"⚠️ {html.escape(w)}" for w in warnings]

    messages, current = [], header
    for block in blocks + (["\n".join(footer)] if footer else []):
        candidate = f"{current}\n\n{block}"
        if len(candidate) > TELEGRAM_LIMIT:
            messages.append(current)
            current = block
        else:
            current = candidate
    messages.append(current)
    return messages


def send_telegram(messages: list[str], token: str, chat_id: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for text in messages:
        resp = requests.post(
            url,
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                  "disable_web_page_preview": True},
            timeout=30,
        )
        if not resp.ok:
            raise RuntimeError(f"Telegram error {resp.status_code}: {resp.text[:200]}")
