"""Page Object Model: each screen is a class that knows its own locators and actions.
Tests say WHAT to do (dashboard.filter("Needs review")); page objects know HOW (which button).
Locators use roles and labels, the same way a screen reader finds things, so they survive CSS
changes and double as a light accessibility check."""
from playwright.sync_api import Page, expect


class BasePage:
    path = "/"

    def __init__(self, page: Page, base_url: str):
        self.page = page
        self.base_url = base_url

    def open(self, path: str | None = None):
        self.page.goto(self.base_url + (path or self.path))
        return self

    @property
    def alert(self):
        return self.page.locator("p.alert")

    def expect_title(self, text: str):
        expect(self.page).to_have_title(text)
