"""End-to-end browser tests against the REAL stack (Angular -> Spring Boot -> database).
Pattern: arrange through the API (fast), act through the UI (what we are testing), assert in both."""
import re
import uuid

import pytest
from playwright.sync_api import expect

from framework.pages.application_detail import ApplicationDetailPage
from framework.pages.dashboard import DashboardPage
from framework.pages.new_application import NewApplicationPage
from testdata.builders import an_applicant

pytestmark = pytest.mark.ui


@pytest.mark.smoke
@pytest.mark.req("CL-US15")
def test_dashboard_tiles_match_the_api(page, ui_url, api, browser_problems):
    stats = api.stats().json()
    dash = DashboardPage(page, ui_url).open().wait_loaded()
    expect(dash.tile("Total")).to_have_text(str(stats["total"]))
    expect(dash.tile("Approved")).to_have_text(str(stats["approved"]))
    expect(dash.tile("Referred")).to_have_text(str(stats["referred"]))
    expect(dash.tile("Declined")).to_have_text(str(stats["declined"]))
    expect(dash.rows).to_have_count(min(10, stats["total"]))
    assert not browser_problems


@pytest.mark.req("CL-US14", "CL-US15")
@pytest.mark.parametrize("label,status", [("Needs review", "REFERRED"), ("Approved", "APPROVED"), ("Declined", "DECLINED")])
def test_status_filter_shows_only_that_status(page, ui_url, label, status):
    dash = DashboardPage(page, ui_url).open().wait_loaded()
    dash.filter(label)
    expect(dash.rows.first.locator(".badge")).to_have_text(status)
    assert set(dash.statuses_shown()) == {status}


@pytest.mark.req("CL-US14")
def test_pager_moves_between_pages(page, ui_url, api):
    total = api.stats().json()["total"]
    if total <= 10:
        pytest.skip("needs more than one page of data")
    dash = DashboardPage(page, ui_url).open().wait_loaded()
    expect(dash.pager_text).to_contain_text("Page 1 of")
    first = dash.rows.first.inner_text()
    dash.next_page()
    expect(dash.pager_text).to_contain_text("Page 2 of")
    assert dash.rows.first.inner_text() != first
    dash.previous_page()
    expect(dash.pager_text).to_contain_text("Page 1 of")


@pytest.mark.req("CL-US10", "CL-US03")
def test_live_preview_follows_the_credit_score(page, ui_url):
    form = NewApplicationPage(page, ui_url).open().wait_loaded()
    form.fill({"annualIncome": 120000, "monthlyDebtPayments": 500, "requestedAmount": 10000, "termMonths": 36})
    for score, outcome, codes in [(760, "APPROVED", []), (640, "REFERRED", ["CS02"]), (580, "DECLINED", ["CS01"])]:
        form.fill({"creditScore": score})
        expect(form.preview_outcome).to_have_text(outcome)
        assert form.preview_reason_codes() == codes


@pytest.mark.req("CL-US01", "CL-US11", "CL-US12")
def test_apply_refer_then_underwriter_approves(page, ui_url, api, browser_problems):
    data = an_applicant().persona("near-prime borrower").build()
    form = NewApplicationPage(page, ui_url).open().wait_loaded()
    form.fill(data)
    expect(form.preview_outcome).to_have_text("REFERRED")
    form.submit()

    detail = ApplicationDetailPage(page, ui_url)
    expect(page).to_have_url(re.compile(r"/applications/\d+$"))
    detail.wait_loaded()
    expect(detail.status).to_have_text("REFERRED")
    expect(detail.reference).to_have_text(re.compile(r"^CL-[0-9A-F]{10}$"))
    app_id = int(page.url.rsplit("/", 1)[1])

    detail.review("J. Rowe", "Verified two recent pay stubs", approve=True)
    expect(detail.status).to_have_text("APPROVED")
    expect(detail.review_form).to_have_count(0)                 # form disappears once decided
    expect(detail.audit_entries).to_have_count(2)
    expect(detail.audit_entries.nth(1)).to_contain_text("Manual review")
    expect(detail.audit_entries.nth(1)).to_contain_text("Verified two recent pay stubs")

    saved = api.get_application(app_id).json()                    # the UI told the truth
    assert saved["status"] == "APPROVED" and saved["decidedBy"] == "J. Rowe"
    assert saved["applicantName"] == data["applicantName"]
    assert not browser_problems


@pytest.mark.req("CL-US11")
def test_review_buttons_disabled_until_name_and_note(page, ui_url, referred_application):
    detail = ApplicationDetailPage(page, ui_url).open_id(referred_application["id"]).wait_loaded()
    approve = detail.review_form.get_by_role("button", name="Approve")
    expect(approve).to_be_disabled()
    detail.review_form.get_by_label("Underwriter name").fill("J. Rowe")
    expect(approve).to_be_disabled()
    detail.review_form.get_by_label("Decision note").fill("Checked")
    expect(approve).to_be_enabled()


@pytest.mark.req("CL-US13")
def test_client_side_validation_blocks_submit(page, ui_url, api):
    before = api.stats().json()["total"]
    form = NewApplicationPage(page, ui_url).open().wait_loaded()
    form.fill({"applicantName": "", "email": "not-an-email", "creditScore": 950})
    form.submit()
    expect(form.alert).to_have_text("Please fix the highlighted fields.")
    expect(form.error_for("applicantName")).to_have_text("Name is required")
    expect(form.error_for("email")).to_have_text("Enter a valid email")
    expect(form.error_for("creditScore")).to_have_text("Between 300 and 900")
    expect(page).to_have_url(re.compile(r"/apply$"))
    assert api.stats().json()["total"] == before


@pytest.mark.req("CL-NFR01")
def test_script_in_applicant_name_is_shown_as_text_not_run(page, ui_url, api, browser_problems):
    # unique tag: earlier runs against the same database leave rows with the same payload
    payload = f"<img src=x onerror=alert('xss')> {uuid.uuid4().hex[:6]}"
    created = api.submit(an_applicant().with_(applicantName=payload).build()).json()
    DashboardPage(page, ui_url).open().wait_loaded()
    expect(page.get_by_role("cell", name=payload)).to_be_visible()
    ApplicationDetailPage(page, ui_url).open_id(created["id"]).wait_loaded()
    expect(page.get_by_text(payload)).to_be_visible()
    page.wait_for_timeout(300)
    assert not browser_problems, browser_problems


@pytest.mark.req("CL-NFR03")
def test_form_can_be_completed_with_the_keyboard_only(page, ui_url):
    form = NewApplicationPage(page, ui_url).open().wait_loaded()
    form.field("applicantName").focus()
    page.keyboard.type("Keyboard User")
    page.keyboard.press("Tab")
    page.keyboard.type("keyboard.user@example.com")
    for _ in range(9):  # tab past the remaining fields to the submit button (defaults are valid)
        if page.evaluate("document.activeElement.type") == "submit":
            break
        page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.textContent.trim()") == "Submit application"
    page.keyboard.press("Enter")
    expect(page).to_have_url(re.compile(r"/applications/\d+$"))
