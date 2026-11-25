from playwright.sync_api import expect

from .base import BasePage


class DashboardPage(BasePage):
    path = "/"

    def tile(self, label: str):
        """Value of a summary tile, e.g. tile('Approved') -> '22'."""
        return self.page.locator(".tile", has=self.page.locator("span", has_text=label)).locator("strong")

    def filter(self, label: str):
        self.page.get_by_role("group", name="Filter by status").get_by_role("button", name=label).click()
        return self

    @property
    def rows(self):
        return self.page.locator("table tbody tr")

    def statuses_shown(self) -> list[str]:
        self.page.wait_for_load_state("networkidle")
        return self.rows.locator(".badge").all_inner_texts()

    def open_application(self, reference: str):
        self.page.get_by_role("link", name=reference).click()
        from .application_detail import ApplicationDetailPage
        return ApplicationDetailPage(self.page, self.base_url)

    @property
    def pager_text(self):
        return self.page.locator(".pager span")

    def next_page(self):
        self.page.get_by_role("button", name="Next").click()

    def previous_page(self):
        self.page.get_by_role("button", name="Previous").click()

    def wait_loaded(self):
        expect(self.page.get_by_role("heading", name="Credit decisions")).to_be_visible()
        return self
