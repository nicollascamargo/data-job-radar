import pytest

from radar.config import DEFAULTS
from radar.matcher import (compare_skills, detect_area, detect_level, evaluate, in_target_city, is_exclusive,
                           outside_brazil, years_required)
from radar.models import Job, norm
from radar.skills import canonical, extract_skills

CONFIG = {
    **DEFAULTS,
    "cities": ["sorocaba", "sao paulo", "campinas", "hortolandia"],
    "my_skills": ["python", "sql", "power bi", "r", "excel", "estatistica"],
}


def job(title, location="Sorocaba, SP", description="", origin="Sorocaba, SP", **kw):
    return Job(site="indeed", title=title, company="ACME", location=location,
               url="https://example.com", description=description, origin=origin, **kw)


@pytest.mark.parametrize("title, area", [
    ("Analista de Dados Jr", "analise"),
    ("Data Analyst - Junior", "analise"),
    ("Analista de BI Júnior", "analise"),
    ("Engenheiro(a) de Dados Júnior", "engenharia"),
    ("Data Engineer I", "engenharia"),
    ("Cientista de Dados Jr", "ciencia"),
    ("Estágio em Ciência de Dados", "ciencia"),
    ("Estagiário(a) de Dados", "geral"),
    ("Vendedor Externo", ""),
])
def test_detect_area(title, area):
    assert detect_area(norm(title)) == area


@pytest.mark.parametrize("title, level", [
    ("Estagiária de Dados", "estagio"),
    ("Data Science Intern", "estagio"),
    ("Analista de Dados Jr", "junior"),
    ("Analista de Dados I", "junior"),
    ("Analista de Dados Jr/Pl", "junior"),
    ("Analista de Dados Sr.", "senior"),
    ("Analista de Dados Pleno", "senior"),
    ("Analista de Dados II", "senior"),
    ("Analista de Dados I/II", "junior"),
    ("Analista Jr I", "junior"),
    ("Analista de Dados Senior I", "senior"),
    ("Analista de Dados Pleno I", "senior"),
    ("CIENTISTA DE DADOS ESPECIALISTA I - GEN AI", "senior"),
    ("Engenheiro de Dados - Tech Lead", "senior"),
    ("Analista de BI", "nao informado"),
])
def test_detect_level_from_title(title, level):
    assert detect_level(norm(title), "", "")[0] == level


def test_level_falls_back_to_linkedin_then_description():
    assert detect_level("analista de dados", "entry level", "") == ("junior", "linkedin")
    assert detect_level("analista de dados", "", "vaga para analista junior") == ("junior", "description")


@pytest.mark.parametrize("text, years", [
    ("experiencia minima de 4 anos com sql", 4),
    ("3+ anos de experiencia em python", 3),
    ("at least 5 years of experience", 5),
    ("primeiro emprego e bem-vindo", None),
])
def test_years_required(text, years):
    assert years_required(text) == years


def test_skills_use_word_boundaries():
    text = "Excelente vaga! Python, SQL e R. Salário R$ 3.000. Estatística."
    assert extract_skills(text) == ["python", "r", "sql", "estatistica"]
    assert extract_skills("Excelente salário R$ 2.000, JavaScript") == []


def test_skills_understand_portuguese_and_english():
    assert extract_skills("aprendizado de máquina e séries temporais") == ["machine learning", "series temporais"]
    assert extract_skills("machine learning and time series forecasting") == ["machine learning", "series temporais"]
    assert extract_skills("redes neurais, LLMs e PLN") == extract_skills("neural networks, LLMs and NLP")
    assert extract_skills("PySpark no Databricks, Power BI, sklearn") == [
        "scikit-learn", "spark", "databricks", "power bi"]


def test_canonical_maps_free_form_names():
    assert canonical(["Power BI", "sklearn", "Python", "llm / ia generativa"]) == {
        "power bi", "scikit-learn", "python", "llm / ia generativa"}


def test_compare_skills_reports_what_is_missing():
    j = job("Engenheiro de Dados Jr", description="Python, SQL, Spark e AWS")
    have, missing, match, points = compare_skills(j, ["python", "sql"])
    assert have == ["python", "sql"] and missing == ["spark", "aws"]
    assert match == 50 and points == 12


def test_job_without_skills_gets_neutral_points():
    assert compare_skills(job("Analista de Dados Jr"), ["python"]) == ([], [], None, 10)


def test_job_asking_mostly_skills_i_lack_is_rejected():
    ev = evaluate(job("Engenheiro de Dados Jr",
                      description="Scala, Spark, Kafka, Databricks, AWS e Airflow. Desejável Python."), CONFIG)
    assert not ev.matched and ev.skill_match == 14 and "airflow" in ev.missing


def test_city_matches_first_part_only():
    assert in_target_city(norm("Campinas, São Paulo, Brazil"), CONFIG["cities"])
    assert not in_target_city(norm("Ribeirão Preto, São Paulo"), CONFIG["cities"])
    assert not in_target_city(norm("Itupeva, SP"), ["itu"]) and in_target_city(norm("Itu, SP"), ["itu"])


def test_good_junior_job_matches():
    ev = evaluate(job("Analista de Dados Júnior", description="Python, SQL e Power BI. Híbrido."), CONFIG)
    assert ev.matched and ev.level == "junior" and ev.modality == "hibrido"
    assert ev.skills == ["python", "sql", "power bi"] and ev.skill_match == 100


def test_senior_job_is_rejected():
    assert not evaluate(job("Cientista de Dados Sênior"), CONFIG).matched


def test_specialist_grade_i_is_rejected():
    ev = evaluate(job("CIENTISTA DE DADOS ESPECIALISTA I - GEN AI"), CONFIG)
    assert not ev.matched and ev.reasons == ["level above junior"]


def test_unspecified_level_with_many_years_is_rejected():
    ev = evaluate(job("Analista de Dados", description="3 anos de experiencia com SQL"), CONFIG)
    assert not ev.matched and "years" in ev.reasons[0]


def test_remote_job_anywhere_matches():
    ev = evaluate(job("Data Engineer Jr", location="Recife, PE", origin="remote",
                      description="100% remoto, Python e SQL"), CONFIG)
    assert ev.matched and ev.modality == "remoto"


def test_onsite_job_outside_target_cities_is_rejected():
    ev = evaluate(job("Analista de Dados Jr", location="Recife, PE", origin="remote"), CONFIG)
    assert not ev.matched


def test_data_entry_is_not_a_data_job():
    assert evaluate(job("Auxiliar de Entrada de Dados"), CONFIG).area == ""


@pytest.mark.parametrize("title", [
    "Analytics Engineer - Brazil – Vaga exclusiva para PCD",
    "Engenheiro (a) de Dados Júnior (Vaga Exclusiva PCD) - Banco de Talentos",
    "Engenheiro de Dados JR (Vaga exclusivo para PCD)",
    "Engenheiro(a) de Dados | Vaga Exclusiva PcD",
    "Analista de Dados | Afirmativa PCD",
    "Analista de Business Intelligence Júnior - Vaga Afirmativa para Pessoas com Deficiência - Allergan Aesthetics",
    "Estágio em Engenharia de Análise de Dados - Vaga afirmativa para mulheres cis e trans",
    "ANALISTA DE DADOS E INTELIGÊNCIA GEOESPACIAL (VAGA AFIRMATIVA PARA MULHERES)",
    "Data Engineer – Brazil – Vaga para mulheres",
    "Grupo QuintoAndar | Senior Data Scientist (Women Applicants Only)",
])
def test_exclusive_titles(title):
    assert is_exclusive(norm(title), "")


@pytest.mark.parametrize("title", [
    "Engenheiro(a) de Dados Júnior",
    "Analista de Inteligência de Dados Júnior",
    "Marketing Analytics Analyst",
    "Analista de Dados Jr - Vaga também para PCD",
])
def test_titles_open_to_everyone(title):
    assert not is_exclusive(norm(title), "")


@pytest.mark.parametrize("description, exclusive", [
    ("Esta vaga é exclusiva para pessoas com deficiência (PCD).", True),
    ("Essa é uma vaga afirmativa para pessoas negras.", True),
    ("Processo seletivo exclusivo para mulheres cis e trans.", True),
    ("Todas as nossas vagas também são abertas a PCD.", False),
    ("Confira também nossas vagas exclusivas para PCD no site.", False),
    ("Não é uma vaga exclusiva para PCD: todas as pessoas podem se candidatar.", False),
    ("Vaga exclusiva para estudantes de Estatística. Incentivamos mulheres a se candidatar.", False),
])
def test_exclusive_only_when_description_says_so(description, exclusive):
    assert is_exclusive(norm("Analista de Dados Jr"), norm(description)) == exclusive


def test_exclusive_job_is_rejected_unless_turned_off():
    j = job("Engenheiro de Dados JR (Vaga exclusivo para PCD)", location="Remoto, BR", origin="remote")
    assert evaluate(j, CONFIG).reasons == ["exclusive job"]
    assert evaluate(j, {**CONFIG, "skip_exclusive_jobs": False}).matched


@pytest.mark.parametrize("location", [
    "United States", "New York, NY", "Seattle, WA", "Washington, DC", "Ohio, United States",
    "Remote - US", "Lisboa, Portugal",
])
def test_locations_outside_brazil(location):
    assert outside_brazil(norm(location))


@pytest.mark.parametrize("location", [
    "São Paulo, São Paulo, Brazil", "Remoto, BR", "Greater São Paulo Area", "Greater Campinas",
    "AM, BR", "Barueri", "Jundiaí", "Sorocaba, SP", "Belém, PA", "Brasil", "",
])
def test_locations_in_brazil(location):
    assert not outside_brazil(norm(location))


def test_remote_job_abroad_is_rejected_unless_turned_off():
    j = job("Remote Data Analyst (Entry-Level / Junior)", location="United States", origin="remote",
            is_remote=True)
    assert evaluate(j, CONFIG).reasons == ["outside Brazil"]
    assert evaluate(j, {**CONFIG, "only_brazil": False}).matched
