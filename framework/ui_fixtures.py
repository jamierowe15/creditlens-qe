"""Browser fixtures shared by the ui, virtual and a11y suites (pytest-playwright provides `page`)."""
from __future__ import annotations

import pytest
import requests

from config import settings
from framework.wiremock import WireMock


def _reachable(url: str) -> bool:
    try:
        return requests.get(url, timeout=3).status_code < 500
    except requests.RequestException:
        return False


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {**browser_context_args, "viewport": {"width": 1280, "height": 900}, "locale": "en-CA", "timezone_id": "America/Toronto"}


@pytest.fixture(scope="session")
def ui_url() -> str:
    if not _reachable(settings.UI_URL):
        pytest.exit(f"CreditLens UI is not reachable at {settings.UI_URL}. Start it with:  python qe.py sut start", returncode=3)
    return settings.UI_URL


@pytest.fixture(scope="session")
def virtual_ui_url() -> str:
    if not WireMock().is_up() or not _reachable(settings.VIRTUAL_UI_URL):
        pytest.exit(f"Virtual environment not running (WireMock {settings.VIRTUAL_API_URL}, UI {settings.VIRTUAL_UI_URL}). "
                    "Start it with:  python qe.py virtual start", returncode=3)
    return settings.VIRTUAL_UI_URL


@pytest.fixture
def wiremock(virtual_ui_url):
    wm = WireMock()
    wm.reset()
    yield wm
    wm.reset()


@pytest.fixture
def browser_problems(page):
    """Collects uncaught JavaScript errors and unexpected dialogs (alert() = a successful XSS)."""
    problems: list[str] = []
    page.on("pageerror", lambda e: problems.append(f"JS error: {e}"))

    def on_dialog(d):
        problems.append(f"Unexpected dialog: {d.type} '{d.message}'")
        d.dismiss()

    page.on("dialog", on_dialog)
    return problems
