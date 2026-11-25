"""Test data management.

Builder pattern: start from a known-good applicant and change only what the test is about.
`an_applicant().with_score(640).build()` reads like the requirement it checks, and every other
field stays at a value that passes all rules, so a failure points at exactly one thing.

All names are fictional; emails use example.com (reserved for testing, never delivered)."""
from __future__ import annotations

import copy
import itertools
import uuid
from dataclasses import dataclass, field

_counter = itertools.count(1)

# A "clean" profile: passes every credit rule with a margin.
BASELINE = {
    "annualIncome": 120000,
    "monthlyDebtPayments": 500,
    "creditScore": 760,
    "requestedAmount": 10000,
    "termMonths": 36,
    "employmentStatus": "FULL_TIME",
    "productType": "PERSONAL_LOAN",
}

# Named personas: shared vocabulary between the BDD feature files, the UI tests and humans.
PERSONAS = {
    "prime borrower":        {},
    "thin-file student":     {"employmentStatus": "STUDENT", "annualIncome": 24000, "creditScore": 688, "requestedAmount": 5000},
    "near-prime borrower":   {"creditScore": 641},
    "subprime borrower":     {"creditScore": 580},
    "self-employed owner":   {"employmentStatus": "SELF_EMPLOYED"},
    "unemployed applicant":  {"employmentStatus": "UNEMPLOYED"},
    "low-income applicant":  {"annualIncome": 18000, "requestedAmount": 5000},
    "over-leveraged borrower": {"monthlyDebtPayments": 5200},
}


@dataclass
class ApplicantBuilder:
    data: dict = field(default_factory=lambda: copy.deepcopy(BASELINE))
    with_identity: bool = True
    removed: set = field(default_factory=set)

    # fluent setters -------------------------------------------------------------------------
    def with_(self, **overrides) -> "ApplicantBuilder":
        self.data.update(overrides)
        return self

    def with_score(self, score: int) -> "ApplicantBuilder":
        return self.with_(creditScore=score)

    def with_income(self, income) -> "ApplicantBuilder":
        return self.with_(annualIncome=income)

    def with_debt(self, monthly) -> "ApplicantBuilder":
        return self.with_(monthlyDebtPayments=monthly)

    def requesting(self, amount, months: int | None = None) -> "ApplicantBuilder":
        self.data["requestedAmount"] = amount
        if months is not None:
            self.data["termMonths"] = months
        return self

    def employed_as(self, status: str) -> "ApplicantBuilder":
        return self.with_(employmentStatus=status)

    def for_product(self, product: str) -> "ApplicantBuilder":
        return self.with_(productType=product)

    def persona(self, name: str) -> "ApplicantBuilder":
        if name not in PERSONAS:
            raise KeyError(f"Unknown persona '{name}'. Known: {', '.join(PERSONAS)}")
        return self.with_(**PERSONAS[name])

    def without(self, *fields: str) -> "ApplicantBuilder":
        for f in fields:
            self.data.pop(f, None)
            self.removed.add(f)
        return self

    def financials_only(self) -> "ApplicantBuilder":
        self.with_identity = False
        return self

    # output ---------------------------------------------------------------------------------
    def build(self) -> dict:
        body = copy.deepcopy(self.data)
        if self.with_identity:
            n = next(_counter)
            if "applicantName" not in self.removed:
                body.setdefault("applicantName", f"QE Applicant {n:04d}")
            if "email" not in self.removed:
                # unique per run so tests never collide, and easy to spot (qe.) in the database
                body.setdefault("email", f"qe.{uuid.uuid4().hex[:10]}@example.com")
        else:
            body.pop("applicantName", None)
            body.pop("email", None)
        return body


def an_applicant() -> ApplicantBuilder:
    return ApplicantBuilder()


def financials() -> ApplicantBuilder:
    return ApplicantBuilder().financials_only()
