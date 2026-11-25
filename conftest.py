"""Shared fixtures for every suite. pytest loads this file automatically."""
from __future__ import annotations

import pytest

from config import settings
from framework.api_client import CreditLensApi
from framework.traceability import TraceabilityPlugin

pytest_plugins = ["framework.ui_fixtures"]


def pytest_configure(config):
    config.pluginmanager.register(TraceabilityPlugin(), "qe-traceability")


@pytest.fixture(scope="session")
def api() -> CreditLensApi:
    """Client for the REAL CreditLens API. Stops the run with a clear message if it is not up,
    instead of 100 confusing connection errors."""
    client = CreditLensApi(settings.API_URL)
    if not client.is_up():
        pytest.exit(f"CreditLens API is not reachable at {settings.API_URL}/actuator/health. "
                    "Start it with:  python qe.py sut start", returncode=3)
    return client


@pytest.fixture
def referred_application(api) -> dict:
    """Arrange step shared by many tests: a freshly submitted application the engine REFERRED."""
    from testdata.builders import an_applicant
    r = api.submit(an_applicant().persona("near-prime borrower").build())
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "REFERRED", body
    return body


def pytest_bdd_apply_tag(tag, function):
    """Gherkin tag '@req:CL-US03' -> @pytest.mark.req('CL-US03'), so BDD scenarios feed the traceability matrix."""
    if tag.startswith("req:"):
        pytest.mark.req(tag.split(":", 1)[1])(function)
        return True
    return None
