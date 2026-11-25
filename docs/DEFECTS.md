# Defect log: CreditLens

Defects found by the CreditLens QE suite. Each one has a **strict xfail** test: the build stays green
while the defect is open, and the test turns red (XPASS) the day the fix lands, so nobody forgets
to close the defect and remove the marker.

| ID | Title | Severity | Priority | Status | Found by |
|---|---|---|---|---|---|
| DEF-001 | Loan-to-income and DTI are rounded before the threshold check | Low | P3 | Open, needs product owner decision | `test_lti_one_dollar_over_half_of_income_refers` |
| DEF-002 | Header logo link's accessible name hides its visible text (WCAG 2.5.3) | Medium | P2 | Open | `test_logo_link_name_contains_its_visible_text` |

---

## DEF-001: Loan-to-income and DTI are rounded before the threshold check

**Component:** backend, `decision/LoanMath.ratio()` used by `LoanToIncomeRule` and `DebtToIncomeRule`
**Rules version:** 2026.11-v1 | **Environment:** local, H2 | **Severity:** Low | **Priority:** P3

**Requirement:** CL-US05, "Requested amount above 50% of annual income refers with LTI2".

**Steps to reproduce**
1. `POST /api/decisions/preview` with annualIncome `120000`, requestedAmount `60001`, creditScore `760`,
   monthlyDebtPayments `500`, termMonths `36`, FULL_TIME, PERSONAL_LOAN.
2. Look at `outcome` and `reasons`.

**Expected:** `REFERRED` with `LTI2`. $60,001 is above 50% of $120,000.
**Actual:** `APPROVED`, no reasons.

**Root cause:** `LoanMath.ratio()` rounds to 4 decimal places (HALF_UP) and the rule compares the
*rounded* value: 60001 / 120000 = 0.500008, which becomes 0.5000, and `0.5000 > 0.50` is false.
Any request up to about $5.99 over the line passes. DTI uses the same code path.

**Impact:** small (a few dollars), but credit policy is a regulated control. An auditor reading the
policy table would expect a strict comparison.

**Suggested fix:** compare the unrounded ratio, or compare amounts directly
(`requestedAmount > annualIncome * 0.50`) and keep the 4-decimal value only for display.
Product owner to confirm the intended behaviour.

---

## DEF-002: Header logo link's accessible name hides its visible text

**Component:** frontend, `app.ts` header | **Standard:** WCAG 2.1 SC 2.5.3 *Label in Name* (Level A)
**Found by:** axe-core rule `label-content-name-mismatch` (impact: serious) on every screen
**Severity:** Medium | **Priority:** P2

**Steps to reproduce**
1. Open any CreditLens page.
2. Inspect the header link: `<a class="brand" aria-label="CreditLens home">CL CreditLens Credit Decisions</a>`.

**Expected:** the accessible name contains the visible text, so a voice-control user can say
"click CreditLens" and hit it.
**Actual:** `aria-label` replaces the visible text with "CreditLens home". axe reports
"Text inside the element is not included in the accessible name".

**Suggested fix:** `aria-label="CreditLens Credit Decisions, home"` or remove the `aria-label` and
mark the "CL" logo `aria-hidden` (it already is).

---

### Template for new defects

```
## DEF-00X: <one-line summary of what is wrong>
Component | Environment | Build / rules version | Severity | Priority
Requirement: <CL-...>
Steps to reproduce: 1. 2. 3.
Expected: | Actual:
Evidence: test id, screenshot / Playwright trace from reports/playwright/, correlation id from the API log
Suggested fix / notes
```

Severity = impact on the user or the bank. Priority = how soon to fix. They are not the same thing:
a typo on the login page is low severity but high priority.
