"""Test oracle: an independent, written-from-the-spec model of the CreditLens decision policy.

A test needs to know the RIGHT answer before it can say the system is wrong. For a handful of
cases we write the expected answer by hand (see test_decision_rules.py). For hundreds of
generated combinations we ask this oracle instead, and compare it with what the API returns
("model-based testing"). The oracle is built from the policy table in the CreditLens README
(rules version 2026.11-v1), NOT copied from the Java code, so a bug in the code is not
silently repeated here.
"""
from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal, getcontext

getcontext().prec = 16

RULES_VERSION = "2026.11-v1"

SEVERITY = {
    "INC1": "DECLINE", "EMP1": "DECLINE", "EMP2": "REFER",
    "CS01": "DECLINE", "CS02": "REFER",
    "DTI1": "DECLINE", "DTI2": "REFER",
    "LTI1": "DECLINE", "LTI2": "REFER",
}

# Pricing policy: base APR by credit-score band, then a product adjustment (percentage points).
APR_BANDS = [(760, Decimal("7.49")), (700, Decimal("9.49")), (660, Decimal("12.99")), (600, Decimal("16.99")), (0, Decimal("21.99"))]
PRODUCT_ADJ = {"PERSONAL_LOAN": Decimal("0.00"), "CAR_LOAN": Decimal("-2.00"), "LINE_OF_CREDIT": Decimal("-1.00")}
RATIO_CAP = Decimal("9.9999")


def _d(v) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v))


def _round(v: Decimal, places: str) -> Decimal:
    return v.quantize(Decimal(places), rounding=ROUND_HALF_UP)


def apr(score: int, product: str) -> Decimal:
    base = next(rate for floor, rate in APR_BANDS if score >= floor)
    return base + PRODUCT_ADJ[product]


def monthly_payment(principal, apr_percent: Decimal, months: int) -> Decimal:
    """Amortized payment M = P*r / (1 - (1+r)^-n), rounded half-up to the cent."""
    p = _d(principal)
    if apr_percent == 0:
        return _round(p / months, "0.01")
    r = apr_percent / 100 / 12
    return _round(p * r / (1 - (1 + r) ** -months), "0.01")


def ratio(num: Decimal, den: Decimal) -> Decimal:
    if den == 0:
        return RATIO_CAP
    return min(_round(num / den, "0.0001"), RATIO_CAP)


def expected(profile: dict) -> dict:
    income = _d(profile["annualIncome"])
    debt = _d(profile["monthlyDebtPayments"])
    score = int(profile["creditScore"])
    amount = _d(profile["requestedAmount"])
    months = int(profile["termMonths"])
    employment = profile["employmentStatus"]

    rate = apr(score, profile["productType"])
    payment = monthly_payment(amount, rate, months)
    monthly_income = _round(income / 12, "0.01")
    dti = ratio(debt + payment, monthly_income)       # includes the NEW payment
    lti = ratio(amount, income)

    codes: list[str] = []
    if income < 20000:
        codes.append("INC1")
    if employment == "UNEMPLOYED":
        codes.append("EMP1")
    elif employment in ("SELF_EMPLOYED", "STUDENT"):
        codes.append("EMP2")
    if score < 600:
        codes.append("CS01")
    elif score < 660:
        codes.append("CS02")
    if dti > Decimal("0.50"):
        codes.append("DTI1")
    elif dti > Decimal("0.40"):
        codes.append("DTI2")
    if lti > Decimal("1.00"):
        codes.append("LTI1")
    elif lti > Decimal("0.50"):
        codes.append("LTI2")

    severities = {SEVERITY[c] for c in codes}
    outcome = "DECLINED" if "DECLINE" in severities else "REFERRED" if "REFER" in severities else "APPROVED"

    def clamp(v: float) -> float:
        return max(0.0, min(100.0, v))

    blend = clamp((900 - score) / 6.0) * 0.50 + clamp(float(dti) * 200) * 0.35 + clamp(float(lti) * 100) * 0.15
    risk = math.floor(blend + 0.5)  # Java Math.round rounds .5 up; Python round() would not

    return {
        "outcome": outcome,
        "codes": set(codes),
        "apr": rate,
        "monthlyPayment": payment,
        "dtiRatio": dti,
        "riskScore": int(risk),
        "approvedAmount": amount if outcome == "APPROVED" else None,
    }


def debt_for_dti(target_dti: str, profile: dict) -> Decimal:
    """Existing monthly debt that puts (debt + new payment) / monthly income exactly at target_dti.
    Lets a boundary test land precisely on 40.00% or 50.00% without guessing."""
    p = dict(profile)
    rate = apr(int(p["creditScore"]), p["productType"])
    payment = monthly_payment(p["requestedAmount"], rate, int(p["termMonths"]))
    monthly_income = _round(_d(p["annualIncome"]) / 12, "0.01")
    return _round(_d(target_dti) * monthly_income - payment, "0.01")
