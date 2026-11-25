"""Contract tests: status codes, headers and JSON shapes the Angular app (and any other client) relies on."""
from decimal import Decimal

import pytest

from framework.schema import assert_matches
from testdata.builders import an_applicant, financials

pytestmark = pytest.mark.api


@pytest.mark.req("CL-US01")
def test_submit_returns_201_with_location_and_contract(api):
    body = an_applicant().build()
    r = api.submit(body)

    assert r.status_code == 201, r.text
    assert r.headers["Location"].endswith(f"/api/applications/{r.json()['id']}")
    created = r.json()
    assert_matches("application", created)
    assert created["applicantName"] == body["applicantName"]
    assert Decimal(str(created["requestedAmount"])) == Decimal(str(body["requestedAmount"]))


def _micros(ts: str) -> str:
    """'2026-11-25T22:27:01.123456789Z' -> '2026-11-25T22:27:01.123456' (database precision)."""
    base, _, frac = ts.rstrip("Z").partition(".")
    return f"{base}.{(frac + '000000')[:6]}"


@pytest.mark.req("CL-US01")
def test_location_header_points_at_the_saved_application(api):
    r = api.submit(an_applicant().build())
    fetched = api.session.get(r.headers["Location"], timeout=10)
    assert fetched.status_code == 200
    created, saved = r.json(), fetched.json()
    # The create response carries Java's nanosecond clock; the database keeps microseconds.
    # Compare timestamps at database precision and everything else exactly.
    for ts in ("createdAt", "updatedAt"):
        assert _micros(saved.pop(ts)) == _micros(created.pop(ts)), ts
    assert saved == created


@pytest.mark.req("CL-US01", "CL-NFR01")
def test_email_is_masked_and_never_returned_in_plain_text(api):
    body = an_applicant().with_(email="Taylor.Morgan@Example.com").build()
    created = api.submit(body).json()
    assert created["emailMasked"] == "t************@example.com"  # first letter + one * per hidden character (12)
    assert "taylor.morgan" not in str(created).lower()
    assert "email" not in created


@pytest.mark.req("CL-US10")
def test_preview_matches_contract(api):
    r = api.preview(financials().build())
    assert r.status_code == 200
    assert_matches("preview", r.json())


@pytest.mark.req("CL-US12")
def test_audit_matches_contract(api):
    created = api.submit(an_applicant().build()).json()
    r = api.audit(created["id"])
    assert r.status_code == 200
    assert_matches("audit", r.json())


@pytest.mark.req("CL-US14")
def test_list_matches_contract(api):
    r = api.list(page=0, size=5)
    assert r.status_code == 200
    assert_matches("page", r.json())


@pytest.mark.req("CL-US15")
def test_stats_matches_contract(api):
    r = api.stats()
    assert r.status_code == 200
    assert_matches("stats", r.json())


@pytest.mark.req("CL-US13")
def test_errors_use_rfc9457_problem_json(api):
    r = api.submit({})
    assert r.status_code == 400
    assert r.headers["Content-Type"].startswith("application/problem+json")
    assert_matches("problem", r.json())
