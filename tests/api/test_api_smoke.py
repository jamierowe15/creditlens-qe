"""Smoke tests: is the system up and observable? These run first; if they fail, nothing else will."""
import re

import pytest

pytestmark = [pytest.mark.api, pytest.mark.smoke]


@pytest.mark.req("CL-NFR05")
def test_health_reports_up(api):
    r = api.health()
    assert r.status_code == 200
    assert r.json()["status"] == "UP"


@pytest.mark.req("CL-NFR05")
def test_decision_metrics_are_exposed_for_monitoring(api):
    api.preview({"annualIncome": 90000, "monthlyDebtPayments": 0, "creditScore": 760, "requestedAmount": 5000,
                 "termMonths": 24, "employmentStatus": "FULL_TIME", "productType": "CAR_LOAN"})
    r = api.get("/actuator/prometheus", headers={"Accept": "text/plain"})
    assert r.status_code == 200
    assert "creditlens_decision_latency" in r.text, "rules-engine latency timer missing from Prometheus output"


@pytest.mark.req("CL-NFR05")
def test_every_response_returns_a_correlation_id(api):
    r = api.stats()
    assert re.fullmatch(r"[A-Za-z0-9-]{8,64}", r.headers.get("X-Correlation-Id", "")), r.headers


@pytest.mark.req("CL-NFR05")
def test_a_valid_incoming_correlation_id_is_echoed_back(api):
    r = api.stats(correlation_id="qe-trace-12345678")
    assert r.headers["X-Correlation-Id"] == "qe-trace-12345678"
