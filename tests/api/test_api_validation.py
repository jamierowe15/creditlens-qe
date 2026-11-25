"""Negative testing: the server must reject bad input on its own, whatever the UI does.
Equivalence partitions: for each field, one value just outside each valid range, wrong types,
missing values. Every case must return 400 and name the offending field."""
import pytest

from testdata.builders import an_applicant

pytestmark = pytest.mark.api

INVALID_FIELDS = [
    # (case id, field, bad value)
    ("score-below-300", "creditScore", 299),
    ("score-above-900", "creditScore", 901),
    ("amount-below-1000", "requestedAmount", 999.99),
    ("amount-above-100000", "requestedAmount", 100000.01),
    ("term-below-6", "termMonths", 5),
    ("term-above-84", "termMonths", 85),
    ("negative-income", "annualIncome", -1),
    ("negative-debt", "monthlyDebtPayments", -0.01),
    ("income-three-decimals", "annualIncome", 50000.123),
    ("blank-name", "applicantName", "   "),
    ("name-101-chars", "applicantName", "A" * 101),
    ("bad-email", "email", "not-an-email"),
    ("blank-email", "email", ""),
    ("null-score", "creditScore", None),
    ("null-employment", "employmentStatus", None),
]


@pytest.mark.req("CL-US13")
@pytest.mark.parametrize("case,field,value", INVALID_FIELDS, ids=[c[0] for c in INVALID_FIELDS])
def test_invalid_field_is_rejected_and_named(api, case, field, value):
    r = api.submit(an_applicant().with_(**{field: value}).build())
    assert r.status_code == 400, f"{case}: expected 400, got {r.status_code} {r.text[:200]}"
    problem = r.json()
    assert problem["title"] == "Validation failed"
    assert field in problem.get("errors", {}), f"{case}: errors={problem.get('errors')}"


@pytest.mark.req("CL-US13")
@pytest.mark.parametrize("field", ["applicantName", "email", "annualIncome", "monthlyDebtPayments", "creditScore",
                                   "requestedAmount", "termMonths", "employmentStatus", "productType"])
def test_missing_required_field(api, field):
    r = api.submit(an_applicant().without(field).build())
    assert r.status_code == 400
    assert field in r.json().get("errors", {})


@pytest.mark.req("CL-US13")
def test_all_invalid_fields_reported_together(api):
    r = api.submit({"applicantName": "", "email": "x", "creditScore": 10})
    errors = r.json()["errors"]
    assert {"applicantName", "email", "creditScore", "annualIncome", "termMonths"} <= set(errors)


@pytest.mark.req("CL-US13")
@pytest.mark.parametrize("case,raw", [
    ("malformed-json", "{\"applicantName\": "),
    ("unknown-enum", '{"employmentStatus": "ASTRONAUT"}'),
    ("string-for-number", '{"creditScore": "seven hundred"}'),
])
def test_unreadable_body_is_400_not_500(api, case, raw):
    r = api.request("POST", "/api/applications", data=raw, headers={"Content-Type": "application/json"})
    assert r.status_code == 400, f"{case}: {r.status_code} {r.text[:200]}"


@pytest.mark.req("CL-US13")
def test_wrong_content_type_is_415(api):
    r = api.request("POST", "/api/applications", data="a=b", headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 415


@pytest.mark.req("CL-US13")
def test_unknown_application_is_404(api):
    for path in ("/api/applications/987654321", "/api/applications/987654321/audit"):
        r = api.get(path)
        assert r.status_code == 404, path
        assert r.json()["title"] == "Not found"


@pytest.mark.req("CL-US13")
def test_non_numeric_id_is_400(api):
    assert api.get("/api/applications/abc").status_code == 400


@pytest.mark.req("CL-US13")
def test_preview_validates_too(api):
    r = api.preview({"creditScore": 1000})
    assert r.status_code == 400 and "creditScore" in r.json()["errors"]
