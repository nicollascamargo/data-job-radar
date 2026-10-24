"""Formats the matched jobs and sends them through a Telegram bot."""

from __future__ import annotations

import html
import logging
from datetime import date

import requests

from .matcher import AREA_LABELS
from .models import Evaluation, Job

log = logging.getLogger(__name__)

TELEGRAM_LIMIT = 4000  # Telegram allows 4096 characters per message
LEVEL_LABELS = {"estagio": "Estágio", "junior": "Júnior", "nao informado": "Nível não informado"}
MODALITY_LABELS = {"remoto": "Remoto", "hibrido": "Híbrido", "presencial": "Presencial"}
SITE_LABELS = {"linkedin": "LinkedIn", "indeed": "Indeed", "glassdoor": "Glassdoor", "adzuna": "Adzuna",
               "gupy": "Gupy"}
URGENT_DAYS = 5          # a deadline closer than this gets a warning


def _day(iso: str) -> date | None:
    try:
        return date.fromisoformat(iso[:10])
    except ValueError:
        return None


def timing(job: Job, today: date | None = None) -> str:
    """'publicada hoje · inscrições até 20/11': applying early is the cheapest edge there is."""
    today = today or date.today()
    parts = []
    posted = _day(job.date_posted)
    if posted:
        days = (today - posted).days
        parts.append("publicada hoje" if days <= 0 else "publicada ontem" if days == 1 else f"publicada há {days} dias")
    deadline = _day(job.deadline)
    if deadline:
        left = (deadline - today).days
        when = f"inscrições até {deadline:%d/%m}"
        parts.append(f"⚠️ {when} (faltam {left} dias)" if 0 <= left < URGENT_DAYS else when)
    return " · ".join(parts)


def format_job(job: Job, ev: Evaluation, today: date | None = None) -> str:
    e = html.escape
    place = "Remoto" if ev.modality == "remoto" else f"{job.location or job.origin} · {MODALITY_LABELS[ev.modality]}"
    lines = [
        f"<b>{e(job.title)}</b>",
        f"🏢 {e(job.company or 'Empresa não informada')} · 📍 {e(place)}",
        f"🎯 {LEVEL_LABELS.get(ev.level, ev.level)} · {AREA_LABELS.get(ev.area, ev.area)} · <b>{ev.score}/100</b>",
    ]
    if ev.skill_match is not None:
        have = f": {e(', '.join(ev.skills))}" if ev.skills else ""
        lines.append(f"🧩 Você tem {ev.skill_match}% das skills{have}")
        if ev.missing:
            lines.append(f"📚 Falta: {e(', '.join(ev.missing))}")
    else:
        lines.append("🧩 Vaga sem lista de skills — vale abrir e conferir")
    when = timing(job, today)
    if when:
        lines.append(f"🕒 {e(when)}")
    lines.append(f'🔗 <a href="{e(job.url, quote=True)}">Ver na vaga ({SITE_LABELS.get(job.site, job.site)})</a>')
    return "\n".join(lines)


def build_messages(matches: list[tuple[Job, Evaluation]], extra: int,
                   warnings: list[str]) -> list[str]:
    """Splits the alert into Telegram-sized messages."""
    if matches:
        interns = sum(1 for _, ev in matches if ev.level == "estagio")
        detail = f" · {interns} de estágio" if interns else ""
        header = (f"🔎 <b>{len(matches) + extra} vaga(s) nova(s) de dados</b>{detail}\n"
                  "O CV de cada uma fica pronto no app Minhas Vagas na próxima busca dele.")
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
