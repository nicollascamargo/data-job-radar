"""Turns a CV into profile.yaml: the list of skills the radar compares against each job.

Only the skills are saved. The CV itself (name, phone, e-mail) never goes into the repo.
"""

from __future__ import annotations

import html
import re
import zipfile
from datetime import date
from pathlib import Path

import yaml

from .skills import extract_skills


def read_cv_text(path: str | Path) -> str:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".docx":
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8")
        xml = re.sub(r"</w:p>|<w:br/>|<w:tab/>", "\n", xml)
        return html.unescape(re.sub(r"<[^>]+>", "", xml))
    if suffix == ".pdf":
        from pypdf import PdfReader
        return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8")
    raise ValueError(f"unsupported CV format: {suffix} (use .docx, .pdf, .txt or .md)")


def build_profile(cv_path: str | Path, out_path: str | Path = "profile.yaml") -> list[str]:
    skills = extract_skills(read_cv_text(cv_path))
    header = (
        f"# Generated from my CV on {date.today().isoformat()} by scripts/build_profile.py\n"
        "# Only skills are stored here. Add or remove items freely.\n"
    )
    body = yaml.safe_dump({"skills": skills}, allow_unicode=True, sort_keys=False)
    Path(out_path).write_text(header + body, encoding="utf-8")
    return skills


def load_profile_skills(path: str | Path) -> list[str]:
    path = Path(path)
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [str(s) for s in data.get("skills", [])]
