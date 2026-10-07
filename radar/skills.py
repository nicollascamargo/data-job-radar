"""Vocabulary of data skills, in Portuguese and English.

The same extractor runs on the CV (what I have) and on each job description
(what the job asks for), so both sides speak the same canonical names.
"""

from __future__ import annotations

import re

from .models import norm

# canonical name -> patterns, applied to normalized text (lowercase, no accents)
SKILLS: dict[str, list[str]] = {
    # languages
    "python": [r"\bpython\b"],
    "r": [r"(?<![a-z0-9$&/])r(?![a-z0-9$&+#/])"],
    "sql": [r"\bsql\b"],
    "scala": [r"\bscala\b"],
    "java": [r"\bjava\b(?!\s?script)"],
    "c#": [r"(?<![a-z])c#", r"\.net\b", r"asp\.?net"],
    # databases
    "sql server": [r"sql server", r"\bmssql\b", r"\bt-?sql\b"],
    "mysql": [r"\bmysql\b"],
    "postgresql": [r"\bpostgre(s|sql)?\b"],
    "oracle": [r"\boracle\b"],
    "nosql": [r"\bnosql\b", r"\bmongo(db)?\b", r"\bcassandra\b", r"\bdynamodb\b"],
    # python data stack
    "pandas": [r"\bpandas\b"],
    "numpy": [r"\bnumpy\b"],
    "scikit-learn": [r"scikit[- ]?learn", r"\bsklearn\b"],
    "matplotlib": [r"\bmatplotlib\b", r"\bseaborn\b", r"\bplotly\b"],
    "tensorflow": [r"\btensorflow\b", r"\bkeras\b"],
    "pytorch": [r"\bpytorch\b", r"\btorch\b"],
    "fastapi": [r"\bfastapi\b", r"\bflask\b"],
    # data engineering
    "etl": [r"\betl\b", r"\belt\b", r"pipelines? de dados", r"data pipelines?"],
    "spark": [r"\b(py)?spark\b"],
    "airflow": [r"\bairflow\b"],
    "dbt": [r"\bdbt\b"],
    "kafka": [r"\bkafka\b"],
    "hadoop": [r"\bhadoop\b", r"\bhive\b"],
    "databricks": [r"\bdatabricks\b"],
    "snowflake": [r"\bsnowflake\b"],
    "bigquery": [r"\bbig ?query\b"],
    "data warehouse": [r"data ?warehouse", r"data ?lake", r"lakehouse"],
    "modelagem de dados": [r"modelagem (de dados|dimensional)", r"data model(l)?ing", r"\bstar schema\b"],
    # cloud and tooling
    "aws": [r"\baws\b", r"amazon web services", r"\bredshift\b", r"\bglue\b"],
    "azure": [r"\bazure\b", r"\bdata factory\b"],
    "gcp": [r"\bgcp\b", r"google cloud"],
    "docker": [r"\bdocker\b", r"\bcontainers?\b"],
    "linux": [r"\blinux\b"],
    "git": [r"\bgit\b", r"\bgithub\b", r"\bgitlab\b"],
    "ci/cd": [r"\bci/cd\b", r"continuous integration", r"integracao continua", r"\bci\b"],
    # analysis and BI
    "excel": [r"\bexcel\b"],
    "power bi": [r"power ?bi\b"],
    "tableau": [r"\btableau\b"],
    "looker": [r"\blooker\b"],
    "qlik": [r"\bqlik"],
    "estatistica": [r"\bestatistic", r"\bstatistic"],
    # machine learning and AI
    "machine learning": [r"machine learning", r"aprendizado de maquina", r"\bml\b"],
    "deep learning": [r"deep learning", r"redes neurais", r"neural networks?"],
    "series temporais": [r"series? temporais", r"time[- ]series", r"\bforecast"],
    "nlp": [r"\bnlp\b", r"processamento de linguagem natural", r"natural language processing"],
    "llm / ia generativa": [r"\bllms?\b", r"ia generativa", r"generative ai", r"\bgenai\b"],
    # languages spoken
    "ingles": [r"\bingles\b", r"\benglish\b"],
    "espanhol": [r"\bespanhol\b", r"\bspanish\b"],
}

_COMPILED = {name: [re.compile(p) for p in patterns] for name, patterns in SKILLS.items()}


def extract_skills(text: str) -> list[str]:
    """Canonical skill names found in the text, in vocabulary order."""
    text = norm(text)
    return [name for name, patterns in _COMPILED.items() if any(p.search(text) for p in patterns)]


def canonical(skills: list[str]) -> set[str]:
    """Maps free-form names ('Power BI', 'sklearn') to canonical ones."""
    found = set(extract_skills(" , ".join(skills)))
    return found | {norm(s) for s in skills if norm(s) in SKILLS}
