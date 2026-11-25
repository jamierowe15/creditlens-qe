from playwright.sync_api import expect

from .base import BasePage

# form field -> accessible label text in the Angular template
LABELS = {
    "applicantName": "Full name",
    "email": "Email",
    "employmentStatus": "Employment",
    "annualIncome": "Annual income",
    "monthlyDebtPayments": "Existing monthly debt payments",
    "creditScore": "Credit score",
    "productType": "Product",
    "requestedAmount": "Amount",
    "termMonths": "Term",
}
SELECTS = {"employmentStatus", "productType"}


class NewApplicationPage(BasePage):
    path = "/apply"

    def field(self, name: str):
        return self.page.get_by_label(LABELS[name])

    def fill(self, data: dict):
        for name, value in data.items():
            if name not in LABELS:
                continue
            if name in SELECTS:
                self.field(name).select_option(value=str(value))
            else:
                self.field(name).fill(str(value))
        return self

    @property
    def preview_card(self):
        return self.page.locator("aside .decision")

    @property
    def preview_outcome(self):
        return self.preview_card.locator(".badge")

    def preview_reason_codes(self) -> list[str]:
        return self.preview_card.locator(".reasons code").all_inner_texts()

    def submit(self):
        self.page.get_by_role("button", name="Submit application").click()

    def error_for(self, name: str):
        return self.page.locator("label", has=self.field(name)).locator(".field-error")

    def wait_loaded(self):
        expect(self.page.get_by_role("heading", name="New credit application")).to_be_visible()
        return self
