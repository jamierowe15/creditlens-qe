"""One place for every URL and threshold. Override any value with an environment variable,
so the same tests run on your laptop, in GitHub Actions, or against a test environment."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default).rstrip("/")


# The real system under test (SUT): CreditLens Spring Boot API + the Angular app in front of it.
API_URL = _env("QE_API_URL", "http://localhost:8080")
UI_URL = _env("QE_UI_URL", "http://localhost:4400")

# The virtualized environment: WireMock pretends to be the API, a second copy of the UI talks to it.
VIRTUAL_API_URL = _env("QE_VIRTUAL_API_URL", "http://localhost:8089")
VIRTUAL_UI_URL = _env("QE_VIRTUAL_UI_URL", "http://localhost:4401")

# Where the CreditLens repo lives (sibling folder by default).
SUT_DIR = Path(os.environ.get("QE_SUT_DIR", ROOT.parent / "creditlens")).resolve()

REPORTS = ROOT / "reports"
REQUEST_TIMEOUT = float(os.environ.get("QE_TIMEOUT", "10"))
