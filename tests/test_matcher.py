import pytest

from radar.config import DEFAULTS
from radar.matcher import detect_area, detect_level, evaluate, find_skills, in_target_city, years_required
from radar.models import Job, norm

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
    text = norm("Excelente vaga! Python, SQL e R. Salário R$ 3.000. Estatística.")
    assert find_skills(text, CONFIG["my_skills"]) == ["python", "sql", "r", "estatistica"]
    assert find_skills(norm("Excelente salário R$ 2.000"), ["r", "excel"]) == []


def test_city_matches_first_part_only():
    assert in_target_city(norm("Campinas, São Paulo, Brazil"), CONFIG["cities"])
    assert not in_target_city(norm("Ribeirão Preto, São Paulo"), CONFIG["cities"])


def test_good_junior_job_matches():
    ev = evaluate(job("Analista de Dados Júnior", description="Python, SQL e Power BI. Híbrido."), CONFIG)
    assert ev.matched and ev.level == "junior" and ev.modality == "hibrido"
    assert ev.skills == ["python", "sql", "power bi"]


def test_senior_job_is_rejected():
    assert not evaluate(job("Cientista de Dados Sênior"), CONFIG).matched


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
