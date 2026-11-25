from playwright.sync_api import expect

from .base import BasePage


class ApplicationDetailPage(BasePage):
    def open_id(self, app_id: int):
        return self.open(f"/applications/{app_id}")

    @property
    def reference(self):
        return self.page.locator(".title-row h1")

    @property
    def status(self):
        return self.page.locator(".title-row .badge")

    @property
    def decided_by(self):
        return self.page.locator(".decision-head .muted")

    @property
    def review_form(self):
        return self.page.locator("form.review")

    def review(self, underwriter: str, note: str, approve: bool = True):
        self.review_form.get_by_label("Underwriter name").fill(underwriter)
        self.review_form.get_by_label("Decision note").fill(note)
        self.review_form.get_by_role("button", name="Approve" if approve else "Decline").click()

    @property
    def review_error(self):
        return self.review_form.locator(".alert")

    @property
    def audit_entries(self):
        return self.page.locator("ol.timeline li")

    def wait_loaded(self):
        expect(self.reference).to_be_visible()
        return self
