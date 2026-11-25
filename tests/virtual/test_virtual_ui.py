"""Service virtualization: the UI runs against WireMock instead of the real API.

Why a bank does this: some states are hard or impossible to create on demand in a shared test
environment (a 500 from a dependency, a 3-second response, a reason code that today's rules
never produce, an empty portfolio). With a virtual service every one of them is one stub away,
and UI testing can start before the backend is even finished."""
import re

import pytest
from playwright.sync_api import expect

from framework.pages.application_detail import ApplicationDetailPage
from framework.pages.dashboard import DashboardPage
from framework.pages.new_application import NewApplicationPage
from framework.schema import assert_matches
from framework.wiremock import WireMock

pytestmark = [pytest.mark.virtual, pytest.mark.ui]

INTERNAL_ERROR = {"type": "about:blank", "title": "Internal error", "status": 500,
                  "detail": "An unexpected error occurred. Quote reference qe-virtual-0001 to support."}


@pytest.mark.req("CL-US15")
def test_dashboard_renders_virtual_portfolio(page, virtual_ui_url, wiremock):
    dash = DashboardPage(page, virtual_ui_url).open().wait_loaded()
    expect(dash.tile("Total")).to_have_text("3")
    expect(dash.tile("Approval rate")).to_have_text("33.3%")
    expect(dash.rows).to_have_count(3)
    assert dash.statuses_shown() == ["DECLINED", "REFERRED", "APPROVED"]


@pytest.mark.req("CL-NFR04")
def test_server_error_shows_safe_message_with_support_reference(page, virtual_ui_url, wiremock):
    wiremock.stub("GET", "/api/applications", 500, INTERNAL_ERROR)
    dash = DashboardPage(page, virtual_ui_url).open().wait_loaded()
    expect(dash.alert).to_have_text(INTERNAL_ERROR["detail"])
    expect(page.get_by_text("Exception")).to_have_count(0)


@pytest.mark.req("CL-NFR04")
def test_api_unreachable_tells_the_user(page, virtual_ui_url, wiremock):
    page.route("**/api/**", lambda route: route.abort("connectionrefused"))   # network-level fault
    dash = DashboardPage(page, virtual_ui_url).open().wait_loaded()
    expect(dash.alert).to_contain_text("Cannot reach the API")


@pytest.mark.req("CL-NFR04")
def test_slow_api_shows_loading_state_then_data(page, virtual_ui_url, wiremock):
    wiremock.stub("GET", "/api/applications", 200,
                  {"content": [], "page": 0, "size": 10, "totalElements": 0, "totalPages": 0}, delay_ms=2500)
    dash = DashboardPage(page, virtual_ui_url).open()
    expect(page.get_by_text("Loading...")).to_be_visible()
    expect(page.get_by_text("No applications match this filter.")).to_be_visible(timeout=8000)


@pytest.mark.req("CL-NFR04", "CL-US13")
def test_server_side_field_error_is_shown_next_to_the_field(page, virtual_ui_url, wiremock):
    wiremock.stub("POST", "/api/applications", 400, {
        "type": "about:blank", "title": "Validation failed", "status": 400, "detail": "One or more fields are invalid.",
        "errors": {"email": "Email domain is not accepted"}})
    form = NewApplicationPage(page, virtual_ui_url).open().wait_loaded()
    form.fill({"applicantName": "Virtual Person", "email": "virtual.person@example.com"})
    form.submit()
    expect(form.alert).to_have_text("One or more fields are invalid.")
    expect(form.error_for("email")).to_have_text("Email domain is not accepted")
    expect(page.get_by_role("button", name="Submit application")).to_be_enabled()  # user can retry


@pytest.mark.req("CL-US02", "CL-US10")
def test_every_reason_code_renders_in_the_preview(page, virtual_ui_url, wiremock):
    """No real applicant triggers all nine codes at once; a stub can."""
    codes = {"INC1": "DECLINE", "EMP1": "DECLINE", "CS01": "DECLINE", "DTI1": "DECLINE", "LTI1": "DECLINE",
             "EMP2": "REFER", "CS02": "REFER", "DTI2": "REFER", "LTI2": "REFER"}
    body = {"outcome": "DECLINED", "riskScore": 100, "dtiRatio": 0.95, "apr": 21.99, "monthlyPayment": 999.99,
            "approvedAmount": None, "rulesVersion": "2026.11-v1",
            "reasons": [{"code": c, "severity": s, "description": f"Virtual reason {c}"} for c, s in codes.items()]}
    assert_matches("preview", body)            # the stub itself must respect the contract
    wiremock.stub("POST", "/api/decisions/preview", 200, body)
    form = NewApplicationPage(page, virtual_ui_url).open().wait_loaded()
    expect(form.preview_outcome).to_have_text("DECLINED")
    assert form.preview_reason_codes() == list(codes)
    expect(form.preview_card.locator("li.sev-decline")).to_have_count(5)
    expect(form.preview_card.locator("li.sev-refer")).to_have_count(4)


@pytest.mark.req("CL-US10")
def test_preview_is_debounced_not_sent_on_every_keystroke(page, virtual_ui_url, wiremock):
    form = NewApplicationPage(page, virtual_ui_url).open().wait_loaded()
    expect(form.preview_outcome).to_have_text("APPROVED")
    wiremock.reset()
    form.field("annualIncome").press_sequentially("123456", delay=40)   # 6 quick keystrokes
    page.wait_for_timeout(1200)
    sent = len(wiremock.requests_to("POST", "/api/decisions/preview"))
    assert 1 <= sent <= 2, f"expected the preview to be debounced, got {sent} calls"


@pytest.mark.req("CL-NFR04", "CL-US11")
def test_conflict_during_review_is_explained(page, virtual_ui_url, wiremock):
    wiremock.stub("POST", "/api/applications/102/review", 409, {
        "type": "about:blank", "title": "Concurrent update", "status": 409,
        "detail": "This application was changed by someone else. Reload it and try again."})
    detail = ApplicationDetailPage(page, virtual_ui_url).open_id(102).wait_loaded()
    detail.review("J. Rowe", "Approving", approve=True)
    expect(detail.review_error).to_have_text("This application was changed by someone else. Reload it and try again.")
    expect(detail.status).to_have_text("REFERRED")


@pytest.mark.req("CL-NFR04")
def test_unknown_application_shows_not_found(page, virtual_ui_url, wiremock):
    wiremock.stub("GET", "/api/applications/999", 404, {"title": "Not found", "status": 404, "detail": "Credit application 999 was not found"})
    page.goto(f"{virtual_ui_url}/applications/999")
    expect(page.locator("p.alert")).to_have_text("Credit application 999 was not found")


@pytest.mark.req("CL-NFR05")
def test_ui_sends_a_correlation_id_with_every_call(page, virtual_ui_url, wiremock):
    DashboardPage(page, virtual_ui_url).open().wait_loaded()
    page.wait_for_load_state("networkidle")
    calls = wiremock.requests_to("GET", "/api/stats") + wiremock.requests_to("GET", "/api/applications")
    assert calls
    for c in calls:
        cid = {k.lower(): v for k, v in c["headers"].items()}.get("x-correlation-id", "")
        assert re.fullmatch(r"[0-9a-f-]{36}", cid), cid


# ------------------------------------------------------------------------------------------
# Keep the virtual service honest: every base stub must match the same contract as the real API
# ------------------------------------------------------------------------------------------
STUB_CONTRACT = {"stats": "stats", "list": "page", "audit-102": "audit", "preview": "preview"}


@pytest.mark.req("CL-US01")
@pytest.mark.parametrize("name,body", [pytest.param(n, b, id=n) for n, b in WireMock().mapping_bodies()])
def test_virtual_stub_matches_contract(name, body):
    if name in STUB_CONTRACT:
        assert_matches(STUB_CONTRACT[name], body)
