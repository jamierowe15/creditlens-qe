"""Step definitions: the glue between plain-English Gherkin lines and the API client.
Business people can read and add Examples rows in the .feature files without touching Python."""
from decimal import Decimal

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from testdata.builders import an_applicant

pytestmark = [pytest.mark.bdd, pytest.mark.api]

scenarios("decision_policy.feature", "underwriter_review.feature")


@pytest.fixture
def ctx():
    return {}


@given("the CreditLens API is running")
def api_running(api):
    assert api.is_up()


@given(parsers.parse('a "{persona}"'))
def persona(ctx, persona):
    ctx["builder"] = an_applicant().persona(persona)


@given(parsers.parse('a "{persona}" with existing monthly debts of {debt:d} and income of {income:d}'))
def persona_with_finances(ctx, persona, debt, income):
    ctx["builder"] = an_applicant().persona(persona).with_debt(debt).with_income(income)


@when("they submit an application")
def submit(api, ctx):
    r = api.submit(ctx["builder"].build())
    assert r.status_code == 201, r.text
    body = r.json()
    ctx["decision"] = {"outcome": body["status"], "reasons": body["reasons"], "dtiRatio": body["dtiRatio"]}


@when(parsers.parse("they preview a loan of {amount:d} over {months:d} months"))
def preview(api, ctx, amount, months):
    body = ctx["builder"].requesting(amount, months).financials_only().build()
    ctx["decision"] = api.preview(body).json()


@then(parsers.parse('the decision is "{outcome}"'))
def decision_is(ctx, outcome):
    assert ctx["decision"]["outcome"] == outcome, ctx["decision"]


@then(parsers.parse('the reasons are "{reasons}"'))
def reasons_are(ctx, reasons):
    want = set() if reasons == "none" else {r.strip() for r in reasons.split(",")}
    assert {r["code"] for r in ctx["decision"]["reasons"]} == want


@then(parsers.parse("the debt-to-income ratio is above {pct:d}%"))
def dti_above(ctx, pct):
    assert Decimal(str(ctx["decision"]["dtiRatio"])) > Decimal(pct) / 100


@given("the portfolio total is noted")
def note_total(api, ctx):
    ctx["total"] = api.stats().json()["total"]


@when(parsers.parse('a "{persona}" previews a decision {times:d} times'))
def preview_many(api, ctx, persona, times):
    for _ in range(times):
        assert api.preview(an_applicant().persona(persona).financials_only().build()).status_code == 200


@then("the portfolio total has not changed")
def total_unchanged(api, ctx):
    assert api.stats().json()["total"] == ctx["total"]


@given(parsers.parse('a "{persona}" has an application that was {status}'))
def existing_application(api, ctx, persona, status):
    body = api.submit(an_applicant().persona(persona).build()).json()
    assert body["status"] == status.upper(), body
    ctx["app"] = body


@when(parsers.parse('underwriter "{name}" chooses to {action} it with note "{note}"'))
def underwriter_acts(api, ctx, name, action, note):
    ctx["review"] = api.review(ctx["app"]["id"], approve=(action == "approve"), underwriter=name, note=note)


@then(parsers.parse('the application status is "{status}"'))
def status_is(api, ctx, status):
    assert api.get_application(ctx["app"]["id"]).json()["status"] == status


@then(parsers.parse('the audit trail shows "{first}" then "{second}" by "{actor}"'))
def audit_shows(api, ctx, first, second, actor):
    trail = api.audit(ctx["app"]["id"]).json()
    assert [e["action"] for e in trail] == [first, second]
    assert trail[-1]["actor"] == actor


@then(parsers.parse('the review is rejected with "{code:d}"'))
def rejected(ctx, code):
    assert ctx["review"].status_code == code
