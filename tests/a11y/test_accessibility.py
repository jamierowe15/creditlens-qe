"""WCAG 2.1 AA scans of every screen and the important states (errors shown, review form open).
Rule: no serious or critical violations. Minor/moderate ones are saved in reports/a11y/ for triage."""
import pytest
from playwright.sync_api import expect

from framework.axe import blocking, describe, scan
from framework.pages.application_detail import ApplicationDetailPage
from framework.pages.dashboard import DashboardPage
from framework.pages.new_application import NewApplicationPage

pytestmark = [pytest.mark.a11y, pytest.mark.ui]


def assert_accessible(page, name):
    result = scan(page, name)
    bad = blocking(result)
    assert not bad, f"{name}: {len(bad)} serious/critical WCAG 2.1 AA violation(s)\n" + describe(bad)


@pytest.mark.req("CL-NFR03")
def test_dashboard_is_accessible(page, ui_url):
    DashboardPage(page, ui_url).open().wait_loaded()
    page.wait_for_load_state("networkidle")
    assert_accessible(page, "dashboard")


@pytest.mark.req("CL-NFR03")
def test_new_application_with_preview_is_accessible(page, ui_url):
    form = NewApplicationPage(page, ui_url).open().wait_loaded()
    expect(form.preview_outcome).to_be_visible()
    assert_accessible(page, "new-application")


@pytest.mark.req("CL-NFR03")
def test_new_application_with_errors_is_accessible(page, ui_url):
    form = NewApplicationPage(page, ui_url).open().wait_loaded()
    form.fill({"applicantName": "", "email": "bad", "creditScore": 10})
    form.submit()
    expect(form.alert).to_be_visible()
    assert_accessible(page, "new-application-errors")


@pytest.mark.req("CL-NFR03")
def test_review_screen_is_accessible(page, ui_url, referred_application):
    ApplicationDetailPage(page, ui_url).open_id(referred_application["id"]).wait_loaded()
    assert_accessible(page, "application-detail-review")


@pytest.mark.req("CL-NFR03")
def test_every_form_control_has_a_label(page, ui_url):
    NewApplicationPage(page, ui_url).open().wait_loaded()
    unlabeled = page.evaluate("""() => [...document.querySelectorAll('input, select, textarea')]
        .filter(el => !(el.labels && el.labels.length) && !el.getAttribute('aria-label') && !el.getAttribute('aria-labelledby'))
        .map(el => el.outerHTML)""")
    assert not unlabeled, unlabeled


@pytest.mark.req("CL-NFR03")
@pytest.mark.defect("DEF-002")
@pytest.mark.xfail(strict=True, reason="DEF-002: header logo link aria-label 'CreditLens home' hides its visible text (WCAG 2.5.3)")
def test_logo_link_name_contains_its_visible_text(page, ui_url):
    DashboardPage(page, ui_url).open().wait_loaded()
    result = scan(page, "brand-link")
    assert not [v for v in blocking(result, include_known=True) if v["id"] == "label-content-name-mismatch"]
