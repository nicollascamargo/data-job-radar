"""Reads your CV and writes profile.yaml with the skills found in it.

    python scripts/build_profile.py meu_curriculo.docx

Run it again whenever you update your CV. Keep the CV itself out of the repo.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar.profile import build_profile  # noqa: E402

if len(sys.argv) != 2:
    sys.exit("usage: python scripts/build_profile.py <cv.docx | cv.pdf | cv.txt>")

skills = build_profile(sys.argv[1], Path(__file__).resolve().parent.parent / "profile.yaml")
print(f"{len(skills)} skills saved to profile.yaml:")
print(", ".join(skills))
