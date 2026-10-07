# Data Job Radar

![Tests](https://github.com/nicollascamargo/data-job-radar/actions/workflows/tests.yml/badge.svg)

A small data pipeline that searches LinkedIn, Indeed, Glassdoor and Adzuna twice a day for **internship and junior data jobs** (data analysis, data engineering, data science), scores each posting against my profile and sends only the good ones to my phone through Telegram.

I built it because checking three job boards every day by hand was slow and I kept missing new postings.

```
🔎 3 vaga(s) nova(s) de dados

Analista de Dados Júnior
🏢 Agro Sorocaba S.A.
📍 Sorocaba, São Paulo, Brazil · Híbrido
🎯 Júnior · Análise de dados · 95/100
🧰 python, sql, sql server, power bi, etl, excel
🔗 Ver no LinkedIn
```

## How it works

```
GitHub Actions (07:07 and 17:07, Brasília time)
   │
   ├─ 1. Collect   JobSpy (LinkedIn, Indeed, Glassdoor) + Adzuna API
   │               3 areas × (Sorocaba, São Paulo, Campinas, Hortolândia + remote in Brazil)
   ├─ 2. Dedupe    SQLite remembers every job seen in the last 30 days,
   │               and the same job posted on two sites counts once
   ├─ 3. Match     rule-based scoring (0–100): role, level, location, my skills
   └─ 4. Notify    Telegram bot, best jobs first, split to fit Telegram's limits
```

**Matching rules** (`radar/matcher.py`)

| Check | Rule |
|---|---|
| Role | Title must be a data role. Data entry, data center and privacy jobs are excluded. |
| Level | Internship or junior from the title, LinkedIn's seniority label or the description. Senior, mid-level (Pleno, II, III), lead and manager titles are dropped. |
| Experience | Jobs with no stated level are dropped if they ask for more than 2 years. |
| Location | Remote anywhere in Brazil, or on-site / hybrid in or near the target cities. |
| Score | level (up to 35) + area (25) + 5 per skill from my profile (up to 25) + location (10). Default cutoff: 45. |

Every data job collected is stored with its extracted skills, which feeds the next step of the project: an analysis of what the Brazilian market asks of junior data professionals.

## Setup (≈10 minutes)

**1. Telegram bot**
1. In Telegram, open **@BotFather**, send `/newbot` and copy the token.
2. Send any message to your new bot.
3. Run `python scripts/get_chat_id.py <TOKEN>` to get your chat id.

**2. Adzuna (optional, free)**
Create an app at [developer.adzuna.com](https://developer.adzuna.com/) and copy the App ID and App Key.

**3. GitHub secrets**
In the repository: *Settings → Secrets and variables → Actions → New repository secret*

| Secret | Required |
|---|---|
| `TELEGRAM_BOT_TOKEN` | yes |
| `TELEGRAM_CHAT_ID` | yes |
| `ADZUNA_APP_ID` | no |
| `ADZUNA_APP_KEY` | no |

**4. First run**
*Actions → Job radar → Run workflow*. After that it runs on its own twice a day.

## Customizing

Everything lives in [`config.yaml`](config.yaml): search terms, cities, radius, sites, levels, skills and the minimum score. Raise `min_score` if alerts get noisy; set `accept_unspecified_level: false` to only see jobs that explicitly say internship or junior.

## Running locally

```bash
pip install -r requirements.txt
python main.py --sample --dry-run   # offline demo with fake jobs
python main.py --dry-run            # real search, prints instead of sending
python main.py --sample             # sends the fake jobs to Telegram to test the bot
pytest -q                           # 40 tests
```

Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` as environment variables to send for real.

## Notes

- Job boards change often and may block automated requests. When a source fails, the run keeps going and the Telegram message says which source failed. If LinkedIn blocks GitHub's servers, add a proxy in `config.yaml`.
- LinkedIn and Glassdoor do not allow scraping in their terms of use. This project is for personal use only, runs twice a day at a slow pace, and never logs in to any account.

## Roadmap

- [ ] Match against my CV with sentence embeddings instead of keyword rules
- [ ] Dashboard of the most requested skills, tools and salaries in junior data jobs
- [ ] Add Gupy, where many Brazilian companies publish their openings

## Stack

Python · pandas · SQLite · JobSpy · Adzuna API · Telegram Bot API · GitHub Actions · pytest
