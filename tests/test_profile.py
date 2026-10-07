import zipfile

import yaml

from radar.config import load_config
from radar.profile import build_profile, read_cv_text

CV_XML = (
    '<?xml version="1.0"?><w:document xmlns:w="w"><w:body>'
    "<w:p><w:r><w:t>Maria Silva &amp; contato: maria@email.com (15) 99999-0000</w:t></w:r></w:p>"
    "<w:p><w:r><w:t>Python (pandas), SQL Server e Power BI</w:t></w:r></w:p>"
    "<w:p><w:r><w:t>English — C1</w:t></w:r></w:p>"
    "</w:body></w:document>"
)


def make_docx(path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", CV_XML)
    return path


def test_reads_docx_text(tmp_path):
    text = read_cv_text(make_docx(tmp_path / "cv.docx"))
    assert "Power BI" in text and "Maria Silva & contato" in text


def test_profile_keeps_only_skills(tmp_path):
    out = tmp_path / "profile.yaml"
    skills = build_profile(make_docx(tmp_path / "cv.docx"), out)
    assert skills == ["python", "sql", "sql server", "pandas", "power bi", "ingles"]
    saved = out.read_text(encoding="utf-8")
    assert "maria" not in saved.lower() and "99999" not in saved   # no personal data
    assert yaml.safe_load(saved)["skills"] == skills


def test_config_merges_profile_and_extra_skills(tmp_path):
    (tmp_path / "profile.yaml").write_text("skills: [python, power bi]\n", encoding="utf-8")
    (tmp_path / "config.yaml").write_text("extra_skills: [Airflow]\n", encoding="utf-8")
    config = load_config(tmp_path / "config.yaml")
    assert config["my_skills"] == ["airflow", "power bi", "python"]
