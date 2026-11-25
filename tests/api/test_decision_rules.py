"""Decision policy tests.

Three techniques, from most to least hand-written:
  1. Boundary-value analysis: the exact values where a rule flips (599/600, 40.00%/40.01% ...).
     Expected results are written BY HAND from the policy table, not computed.
  2. Pricing / math checks: APR table and amortized payment, against hand-worked numbers.
  3. Model-based testing: ~100 generated combinations, each compared with the independent oracle.
"""
import random
from decimal import Decimal

import pytest

from testdata.builders import BASELINE, an_applicant, financials
from testdata.oracle import debt_for_dti, expected

pytestmark = pytest.mark.api


def decide(api, body):
    r = api.preview(body)
    assert r.status_code == 200, r.text
    d = r.json()
    return d["outcome"], {x["code"] for x in d["reasons"]}, d


# --------------------------------------------------------------------------------------------
# 1. Boundary values. Every row: (id, overrides, expected outcome, expected reason codes)
# --------------------------------------------------------------------------------------------
_dti_40 = debt_for_dti("0.40", BASELINE)
_dti_50 = debt_for_dti("0.50", BASELINE)

BOUNDARIES = [
    # Credit score bands (CL-US03)
    ("score-599-declines",   "CL-US03", {"creditScore": 599}, "DECLINED", {"CS01"}),
    ("score-600-refers",     "CL-US03", {"creditScore": 600}, "REFERRED", {"CS02"}),
    ("score-659-refers",     "CL-US03", {"creditScore": 659}, "REFERRED", {"CS02"}),
    ("score-660-passes",     "CL-US03", {"creditScore": 660}, "APPROVED", set()),
    ("score-300-min-valid",  "CL-US03", {"creditScore": 300}, "DECLINED", {"CS01"}),
    ("score-900-max-valid",  "CL-US03", {"creditScore": 900}, "APPROVED", set()),
    # Debt-to-income incl. the new payment (CL-US04)
    ("dti-exactly-40-passes",  "CL-US04", {"monthlyDebtPayments": float(_dti_40)}, "APPROVED", set()),
    ("dti-40.01-refers",       "CL-US04", {"monthlyDebtPayments": float(_dti_40 + 1)}, "REFERRED", {"DTI2"}),
    ("dti-exactly-50-refers",  "CL-US04", {"monthlyDebtPayments": float(_dti_50)}, "REFERRED", {"DTI2"}),
    ("dti-50.01-declines",     "CL-US04", {"monthlyDebtPayments": float(_dti_50 + 1)}, "DECLINED", {"DTI1"}),
    # Loan-to-income (CL-US05): income 120,000 -> 50% = 60,000. Income 50,000 for the 100% line.
    ("lti-exactly-50-passes",  "CL-US05", {"requestedAmount": 60000}, "APPROVED", set()),
    ("lti-50.01-refers",       "CL-US05", {"requestedAmount": 60012}, "REFERRED", {"LTI2"}),
    ("lti-exactly-100-refers", "CL-US05", {"annualIncome": 50000, "monthlyDebtPayments": 0, "requestedAmount": 50000, "termMonths": 84}, "REFERRED", {"LTI2"}),
    ("lti-100.01-declines",    "CL-US05", {"annualIncome": 50000, "monthlyDebtPayments": 0, "requestedAmount": 50005, "termMonths": 84}, "DECLINED", {"LTI1"}),
    # Employment (CL-US06)
    ("full-time-passes",     "CL-US06", {"employmentStatus": "FULL_TIME"}, "APPROVED", set()),
    ("part-time-passes",     "CL-US06", {"employmentStatus": "PART_TIME"}, "APPROVED", set()),
    ("retired-passes",       "CL-US06", {"employmentStatus": "RETIRED"}, "APPROVED", set()),
    ("self-employed-refers", "CL-US06", {"employmentStatus": "SELF_EMPLOYED"}, "REFERRED", {"EMP2"}),
    ("student-refers",       "CL-US06", {"employmentStatus": "STUDENT"}, "REFERRED", {"EMP2"}),
    ("unemployed-declines",  "CL-US06", {"employmentStatus": "UNEMPLOYED"}, "DECLINED", {"EMP1"}),
    # Minimum income (CL-US07). Small loan and no debt so only the income rule can fire.
    ("income-19999.99-declines", "CL-US07", {"annualIncome": 19999.99, "monthlyDebtPayments": 0, "requestedAmount": 1000}, "DECLINED", {"INC1"}),
    ("income-20000-passes",      "CL-US07", {"annualIncome": 20000, "monthlyDebtPayments": 0, "requestedAmount": 1000}, "APPROVED", set()),
    # Worst outcome wins + every reason reported (CL-US08)
    ("decline-beats-refer",  "CL-US08", {"creditScore": 640, "employmentStatus": "UNEMPLOYED"}, "DECLINED", {"CS02", "EMP1"}),
    ("all-refers-reported",  "CL-US08", {"creditScore": 640, "employmentStatus": "STUDENT"}, "REFERRED", {"CS02", "EMP2"}),
]


@pytest.mark.parametrize("case_id,overrides,outcome,codes", [
    pytest.param(cid, ov, out, codes, id=cid, marks=pytest.mark.req(req, "CL-US02")) for cid, req, ov, out, codes in BOUNDARIES])
def test_policy_boundary(api, case_id, overrides, outcome, codes):
    got_outcome, got_codes, detail = decide(api, financials().with_(**overrides).build())
    assert (got_outcome, got_codes) == (outcome, codes), f"{case_id}: DTI={detail['dtiRatio']} reasons={detail['reasons']}"


# Known defect DEF-001: ratios are rounded to 4 decimals BEFORE the threshold comparison,
# so a request up to ~$5.99 over the 50% line is treated as "exactly 50%" and passes.
@pytest.mark.req("CL-US05")
@pytest.mark.defect("DEF-001")
@pytest.mark.xfail(strict=True, reason="DEF-001: LTI rounded to 4 dp before comparing; $60,001 on $120,000 income passes")
def test_lti_one_dollar_over_half_of_income_refers(api):
    outcome, codes, _ = decide(api, financials().requesting(60001).build())
    assert "LTI2" in codes and outcome == "REFERRED"


@pytest.mark.req("CL-US08")
def test_decline_reasons_are_listed_before_refer_reasons(api):
    _, _, d = decide(api, financials().with_(creditScore=640, employmentStatus="UNEMPLOYED", annualIncome=19000,
                                             requestedAmount=1000, monthlyDebtPayments=0).build())
    severities = [r["severity"] for r in d["reasons"]]
    assert severities == sorted(severities, key=lambda s: 0 if s == "DECLINE" else 1), d["reasons"]


@pytest.mark.req("CL-US02")
def test_every_reason_has_a_readable_description(api):
    _, _, d = decide(api, financials().with_(creditScore=580, employmentStatus="STUDENT").build())
    assert d["reasons"], "expected reasons for a subprime student"
    for r in d["reasons"]:
        assert len(r["description"]) > 10 and r["code"] not in r["description"]


@pytest.mark.req("CL-US02")
def test_approved_has_amount_and_no_reasons_declined_has_no_amount(api):
    _, _, ok = decide(api, financials().build())
    _, _, bad = decide(api, financials().with_score(550).build())
    assert ok["reasons"] == [] and Decimal(str(ok["approvedAmount"])) == Decimal(str(BASELINE["requestedAmount"]))
    assert bad["reasons"] and bad["approvedAmount"] is None


# --------------------------------------------------------------------------------------------
# 2. Pricing and loan math (CL-US09), hand-worked expected values
# --------------------------------------------------------------------------------------------
APR_TABLE = [
    (760, "PERSONAL_LOAN", "7.49"), (759, "PERSONAL_LOAN", "9.49"), (700, "CAR_LOAN", "7.49"),
    (699, "LINE_OF_CREDIT", "11.99"), (660, "PERSONAL_LOAN", "12.99"), (659, "CAR_LOAN", "14.99"),
    (600, "PERSONAL_LOAN", "16.99"), (599, "LINE_OF_CREDIT", "20.99"),
]


@pytest.mark.req("CL-US09")
@pytest.mark.parametrize("score,product,apr", APR_TABLE, ids=[f"{s}-{p}" for s, p, _ in APR_TABLE])
def test_apr_follows_score_band_and_product(api, score, product, apr):
    _, _, d = decide(api, financials().with_score(score).for_product(product).build())
    assert Decimal(str(d["apr"])) == Decimal(apr)


@pytest.mark.req("CL-US09")
def test_amortized_payment_hand_worked_example(api):
    # $10,000 over 36 months at 9.49% APR (score 700, personal loan).
    # r = 0.0949/12 = 0.00790833; M = P*r / (1 - (1+r)^-36) = $320.28 (checked with a spreadsheet PMT()).
    _, _, d = decide(api, financials().with_score(700).requesting(10000, 36).build())
    assert Decimal(str(d["monthlyPayment"])) == Decimal("320.28")


@pytest.mark.req("CL-US09")
def test_risk_score_is_between_0_and_100_at_the_extremes(api):
    _, _, best = decide(api, financials().with_(creditScore=900, monthlyDebtPayments=0, requestedAmount=1000).build())
    _, _, worst = decide(api, financials().with_(creditScore=300, monthlyDebtPayments=50000, annualIncome=20000, requestedAmount=100000).build())
    assert 0 <= best["riskScore"] <= 10
    assert worst["riskScore"] == 100


# --------------------------------------------------------------------------------------------
# 3. Model-based testing: generated combinations vs the oracle (CL-US08, CL-US09)
# --------------------------------------------------------------------------------------------
def _generated_profiles(n=100, seed=2026):
    rng = random.Random(seed)  # fixed seed = the same "random" data every run (reproducible)
    dims = {
        "creditScore": [300, 580, 599, 600, 640, 659, 660, 699, 700, 759, 760, 820, 900],
        "annualIncome": [15000, 19999.99, 20000, 35000, 52000, 80000, 150000],
        "monthlyDebtPayments": [0, 250, 800, 1500, 3000],
        "requestedAmount": [1000, 5000, 12500, 30000, 75000, 100000],
        "termMonths": [6, 12, 36, 60, 84],
        "employmentStatus": ["FULL_TIME", "PART_TIME", "SELF_EMPLOYED", "STUDENT", "RETIRED", "UNEMPLOYED"],
        "productType": ["PERSONAL_LOAN", "CAR_LOAN", "LINE_OF_CREDIT"],
    }
    keys = list(dims)
    seen = set()
    while len(seen) < n:
        combo = tuple(rng.choice(dims[k]) for k in keys)
        seen.add(combo)
    return [dict(zip(keys, c)) for c in sorted(seen, key=str)]


GENERATED = _generated_profiles()


@pytest.mark.req("CL-US08", "CL-US09")
@pytest.mark.parametrize("profile", GENERATED, ids=[f"gen{i:03d}" for i in range(len(GENERATED))])
def test_engine_agrees_with_oracle(api, profile):
    want = expected(profile)
    outcome, codes, got = decide(api, profile)
    mismatches = []
    for field, have, exp in [
        ("outcome", outcome, want["outcome"]),
        ("reasons", codes, want["codes"]),
        ("apr", Decimal(str(got["apr"])), want["apr"]),
        ("monthlyPayment", Decimal(str(got["monthlyPayment"])), want["monthlyPayment"]),
        ("dtiRatio", Decimal(str(got["dtiRatio"])), want["dtiRatio"]),
        ("riskScore", got["riskScore"], want["riskScore"]),
    ]:
        if have != exp:
            mismatches.append(f"{field}: api={have} oracle={exp}")
    assert not mismatches, f"profile={profile}\n" + "\n".join(mismatches)


# --------------------------------------------------------------------------------------------
# Preview vs submit (CL-US10)
# --------------------------------------------------------------------------------------------
@pytest.mark.req("CL-US10")
@pytest.mark.parametrize("persona", ["prime borrower", "near-prime borrower", "subprime borrower", "self-employed owner"])
def test_preview_and_submit_agree(api, persona):
    body = an_applicant().persona(persona).build()
    preview = api.preview({k: v for k, v in body.items() if k not in ("applicantName", "email")}).json()
    saved = api.submit(body).json()
    assert saved["status"] == preview["outcome"]
    assert [r["code"] for r in saved["reasons"]] == [r["code"] for r in preview["reasons"]]
    for f in ("riskScore", "apr", "monthlyPayment", "dtiRatio"):
        assert Decimal(str(saved[f])) == Decimal(str(preview[f])), f


@pytest.mark.req("CL-US10")
def test_preview_saves_nothing(api):
    before = api.stats().json()["total"]
    for score in (550, 640, 780):
        assert api.preview(financials().with_score(score).build()).status_code == 200
    assert api.stats().json()["total"] == before


