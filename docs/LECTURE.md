# CreditLens QE: the lecture

This guide teaches everything in this repo, in the order you need it. Every section ends in real
files you can open. Run the framework once first (Part 1), then read with the code open beside you.

The framework is built around TD's **Quality Engineer I** posting (R_1521575). Part 0 maps each line
of that posting to the place in this repo where you did it, so you can talk about it in an interview.

---

## Part 0. What a Quality Engineer does, and where you did it

A QA tester checks software after it is built. A **Quality Engineer** builds the machinery that
checks it all the time: test frameworks, test data, virtual services, pipelines and reports. Developers
get feedback in minutes, not at the end of a project. Banks call this "shift-left" testing: testing
moves earlier (to the left) on the project timeline.

| Posting says | You did it here |
|---|---|
| Test planning, test design/development, automation, execution | `docs/TEST_PLAN.md`, all of `tests/`, `qe.py` |
| Define test data and environment requirements | `testdata/builders.py`, `docs/TEST_PLAN.md` §4-5, `qe.py sut/virtual` |
| Analyze the end-to-end solution to develop in-scope tests | `requirements/requirements.json` was written by reading the CreditLens code, README and API |
| Develop and maintain test suites and traceability matrices; log defects | 8 suites; `framework/traceability.py`; `docs/DEFECTS.md` |
| Use test automation frameworks and test management tools | pytest + plugins; traceability matrix, JUnit XML and HTML reports |
| Leverage virtual assets for incomplete or unavailable services | `virtualization/` + `tests/virtual/` (WireMock) |
| Test data management, reusable data provisioning | builders, personas, seeded generators, contract-checked virtual data |
| DevOps tools, source control, service virtualization, monitoring | Git/GitHub, GitHub Actions, WireMock, actuator health and Prometheus checks |
| Functional and non-functional automation: performance, readiness (ORT), accessibility, security | `tests/perf`, smoke and observability tests, `tests/a11y`, `tests/security` + ZAP |
| Automated tests integrated into CI/CD/CT pipelines | `.github/workflows/qe.yml` |
| Validate user stories, acceptance criteria, DoD/DoR | stories and acceptance criteria in `requirements.json`; Gherkin in `tests/bdd/features` |
| BDD / TDD | pytest-bdd scenarios; strict-xfail tests written *before* a fix (TDD for defects) |
| Feedback, reporting and analytics on quality | `reports/index.html`, traceability, perf report, GitHub run summary |
| Proofs of concept on new tools | the whole repo is a PoC of Python + Playwright + WireMock + Locust for a Java/Angular app |

---

## Part 1. First run

```powershell
powershell -ExecutionPolicy Bypass -File .\Setup-CreditLensQE.ps1
```

What happens, in order:

1. **Prerequisites.** Git, Python 3.11+, JDK 21, Maven and Node 22+ are checked. Anything missing is
   installed with `winget`; Maven is downloaded as a portable zip into `.tools\` if needed. If you ran
   CreditLens' own setup before, its `.local-env.ps1` is reused.
2. **System under test (SUT).** It finds your `creditlens` folder (or clones it next to this one).
3. **Test tools.** It creates `.venv` (a private Python just for this project) and installs the pinned
   versions from `requirements.txt`, then downloads Chromium for Playwright. `npm ci` installs WireMock
   and axe-core from `package-lock.json`.
4. **`python qe.py all`**:
   - builds the CreditLens jar (`mvn package`) and Angular app (`npm run build`) the first time only
   - starts the API on **8080** and serves the UI on **4400**
   - starts **WireMock** on **8089** and a second copy of the UI on **4401** that talks to WireMock
   - runs the suites in pipeline order: smoke → api → bdd → security → ui → virtual → a11y → perf
   - writes `reports/index.html` and the traceability matrix, then stops the servers it started
5. It opens the report.

Expected result: every suite green, with **2 known defects** (xfail). Part 9 explains those.

> Tip: `.\.venv\Scripts\python qe.py test ui --headed` lets you watch the browser tests, slowed down.

---

## Part 2. How the framework is put together

```
            requirements.json  (what must be true)
                   │ ids
   ┌───────────────┴───────────────────────────────────────────────┐
   │ tests/  api  bdd  security  ui  virtual  a11y  perf            │  WHAT to check
   └───┬──────────┬───────────────┬──────────────┬─────────────────┘
       │          │               │              │
 framework/   testdata/       framework/pages  framework/wiremock.py   HOW to talk to things
 api_client   builders,       (page objects)   framework/axe.py
 schema.py    personas,
              oracle
       │          │               │              │
       ▼          ▼               ▼              ▼
   CreditLens API :8080   UI :4400 → :8080   WireMock :8089   UI :4401 → :8089
```

Rules this layout follows (all standard in bank QE teams):

- **Tests never contain URLs, raw JSON or CSS selectors.** Those live in one place each
  (`config/settings.py`, `testdata/`, `framework/pages/`). When the app changes, one file changes,
  not 50 tests.
- **Configuration comes from environment variables** (`QE_API_URL`, `QE_UI_URL` ...), so the same tests
  run on your laptop, in GitHub Actions, or against a shared test environment.
- **One command runs everything** (`qe.py`), on Windows and Linux alike.

`tools/spa_proxy.py` is a small web server: it serves the built Angular files and forwards `/api`
calls to whichever backend you name. That one trick lets the same UI build point at the real API or at
WireMock.

---

## Part 3. pytest in 15 minutes

pytest finds files named `test_*.py` and runs the functions named `test_*`. A plain `assert` is
all you need; pytest prints both sides when it fails.

**Fixtures** set things up. A test asks for one by naming it as a parameter:

```python
@pytest.fixture(scope="session")
def api() -> CreditLensApi:          # conftest.py
    client = CreditLensApi(settings.API_URL)
    if not client.is_up():
        pytest.exit("CreditLens API is not reachable ...")
    return client

def test_health_reports_up(api):      # pytest passes the fixture in
    assert api.health().json()["status"] == "UP"
```

`scope="session"` means it runs once for the whole run. `conftest.py` files hold fixtures shared
by every test below them. `referred_application` in `conftest.py` is an *arrange* fixture: many
tests need a REFERRED application, so they ask for one instead of building it each time.

**Parametrize** runs one test with many inputs. That is how 24 boundary cases share one function:

```python
@pytest.mark.parametrize("case_id,overrides,outcome,codes", [...])
def test_policy_boundary(api, case_id, overrides, outcome, codes): ...
```

**Markers** label tests: `@pytest.mark.ui`, `@pytest.mark.smoke`, `@pytest.mark.req("CL-US03")`.
`pytest -m smoke` runs only smoke tests. `--strict-markers` in `pytest.ini` turns a typo in a marker
into an error instead of a silently ignored label.

**xfail(strict=True)** means "this is expected to fail because of a known defect". If it
unexpectedly passes (someone fixed the bug), *strict* makes the run fail, so the marker gets removed.

**Plugins and hooks.** pytest calls hook functions at each stage. `framework/traceability.py` uses
`pytest_runtest_makereport` to remember each test's requirement ids and `pytest_sessionfinish` to
write the matrix. That is the same mechanism big plugins like pytest-html use.

**Plugins installed here:** pytest-playwright (browser fixtures, screenshots, traces), pytest-bdd
(Gherkin), pytest-html (HTML reports), pytest-rerunfailures (available if a UI test ever needs
`--reruns 1`; we prefer fixing flakiness to hiding it).

---

## Part 4. API and contract testing

Open `tests/api/test_api_contract.py`.

```python
def test_submit_returns_201_with_location_and_contract(api):
    body = an_applicant().build()            # arrange
    r = api.submit(body)                     # act
    assert r.status_code == 201              # assert: status
    assert r.headers["Location"].endswith(f"/api/applications/{r.json()['id']}")   # header
    assert_matches("application", r.json())  # assert: whole shape
```

**Arrange, act, assert** is the shape of almost every test. Keep each part short.

**Contract testing.** `schemas/application.schema.json` is a JSON Schema: a machine-readable
description of the response. It says `creditScore` is an integer from 300 to 900, `referenceNumber`
matches `^CL-[0-9A-F]{10}$`, `approvedAmount` may be null, and **no extra fields are allowed**
(`additionalProperties: false`). That last rule catches the day a developer accidentally starts
returning the raw email. `framework/schema.py` validates every response against its schema and
prints exactly which field broke.

Why it matters at a bank: the Angular app, mobile apps and other teams' services all depend on the
same API. A contract test fails *before* any of them breaks.

**Status codes the suite checks:** 201 Created (+ `Location`), 200 OK, 400 validation (RFC 9457
problem JSON with an `errors` map), 404 not found, 409 conflict (wrong state, or a concurrent update),
415 wrong content type, 405/403 methods not in the contract.

---

## Part 5. Test design: choosing the cases that find bugs

You cannot test every input. Test design picks the few that matter. Open
`tests/api/test_decision_rules.py`.

### 5.1 Boundary-value analysis (BVA)
Bugs cluster at edges: `<` written where `<=` was meant. For "score below 600 declines; 600-659
refers", test **599, 600, 659, 660** (plus the valid extremes 300 and 900). Same for DTI at exactly
40.00% and 40.01%, 50.00% and 50.01%, and income at $19,999.99 and $20,000.

Hitting exactly 40.00% DTI by guessing is hard, because DTI includes the new loan payment.
`testdata/oracle.py: debt_for_dti("0.40", profile)` works out the existing debt that lands there.

### 5.2 Equivalence partitioning (EP)
Inputs fall into groups that behave the same. One value per group is enough. For `termMonths`
(valid 6-84): one below (5), one above (85), missing, wrong type. `tests/api/test_api_validation.py`
does this for every field.

### 5.3 Decision tables
When rules combine, list the combinations. CreditLens says "worst outcome wins": a decline reason
beats a refer reason, and every failing rule is reported. Cases `decline-beats-refer` and
`all-refers-reported` cover it.

### 5.4 State-transition testing
An application is a small state machine:

```
           submit                 review (approve)
  (new) ─────────▶ REFERRED ─────────────────────▶ APPROVED
            │               └──── review (decline) ▶ DECLINED
            ├──────▶ APPROVED   (no transitions out: 409)
            └──────▶ DECLINED   (no transitions out: 409)
```

Test every valid arrow and every forbidden one: `test_review_workflow.py`. The nastiest case is two
underwriters clicking at the same moment. `test_concurrent_reviews_exactly_one_wins` starts two
threads behind a `Barrier` so they fire together, and expects exactly one 200 and one 409.
CreditLens handles it with optimistic locking (`@Version`).

### 5.5 Model-based testing with an oracle
A test needs the right answer before it can call the system wrong. For hand-picked cases we write it
by hand. For 100 generated combinations, `testdata/oracle.py` computes it: an independent model of
the policy written from the README's policy table. `test_engine_agrees_with_oracle` compares outcome,
reasons, APR, payment, DTI and risk score for each one.

The generator uses `random.Random(2026)`: a **fixed seed**, so the "random" cases are identical on
every run. A failure on Tuesday reproduces on Wednesday.

### 5.6 How DEF-001 was found
The spec says "requested amount **above** 50% of income refers". BVA says to test one step above the
line: $60,001 on $120,000 income. CreditLens approved it. The code rounds the ratio to 4 decimals
*before* comparing (0.500008 → 0.5000), so anything up to about $5.99 over the line passes. That is a
defect you can explain in an interview: technique → test → finding → root cause → suggested fix.
See `docs/DEFECTS.md`.

---

## Part 6. Test data management

Open `testdata/builders.py`.

```python
an_applicant().persona("near-prime borrower").build()
financials().with_score(599).build()
an_applicant().without("email").build()
```

- **Builder pattern.** Start from `BASELINE`, a profile that passes every rule with a margin, and change
  only what the test is about. If the test fails, the one thing you changed is the cause.
- **Personas** are shared names for common profiles. The BDD files, UI tests and people all say
  "near-prime borrower" and mean the same data.
- **Unique, recognisable data.** Each applicant gets `qe.<random>@example.com`. `example.com` is reserved
  for testing (it never delivers mail), and the `qe.` prefix makes test rows easy to find or clean up
  in a shared database.
- **No production data, ever.** Banks forbid copying real customer data into test environments
  (privacy law and internal policy). Synthetic data like this is the normal answer.
- **Virtual data is data too.** `virtualization/__files/*.json` is checked against the same schemas as
  the real API (`test_virtual_stub_matches_contract`), so the virtual service cannot drift from the real one.

---

## Part 7. BDD: requirements you can execute

Open `tests/bdd/features/decision_policy.feature`.

```gherkin
Scenario Outline: Each persona gets the decision the policy promises
  Given a "<persona>"
  When they submit an application
  Then the decision is "<outcome>"
  And the reasons are "<reasons>"
  Examples:
    | persona             | outcome  | reasons |
    | near-prime borrower | REFERRED | CS02    |
```

**Gherkin** is structured English: Given (context), When (action), Then (outcome). A business
analyst can read it, and can add a row to `Examples` without touching Python.
`tests/bdd/test_bdd_steps.py` holds the **step definitions** that connect each line to the API
client.

**How it fits an agile team (the "three amigos").** Before a story starts, the product owner, a
developer and the QE agree on acceptance criteria and write them as scenarios.

- **Definition of Ready (DoR):** a story can start only when its acceptance criteria are testable,
  for example "DTI of exactly 40% passes", not "DTI is handled".
- **Definition of Done (DoD):** a story is done only when its scenarios are automated and green in the
  pipeline, and the traceability matrix shows it PASSING.

`requirements/requirements.json` holds the stories and acceptance criteria. Tags like
`@req:CL-US11` link each scenario to its story.

**BDD vs TDD.** TDD (test-driven development) means writing a failing test, then the code that makes
it pass. The strict-xfail tests for DEF-001 and DEF-002 are TDD for defects: the test exists before
the fix, and it goes green when the fix is right.

---

## Part 8. UI automation with Playwright

Open `framework/pages/new_application.py` and `tests/ui/test_ui_e2e.py`.

### 8.1 Locators that don't break
```python
page.get_by_role("button", name="Submit application")
page.get_by_label("Credit score")
```
Find elements the way a screen reader does: by **role** and **accessible name**. These survive CSS and
layout changes, and if one can't be found, that's often an accessibility bug as well. Use CSS only
when there's no role to use (`.badge`).

### 8.2 Auto-waiting assertions
```python
expect(form.preview_outcome).to_have_text("REFERRED")
```
`expect` retries until the condition is true or a timeout passes (5 s by default). This matters
because the live preview waits 350 ms after typing stops, then calls the API. **Never use
`sleep(2)`**: it is slow when the app is fast and still flaky when the app is slow. Auto-waiting is
the main reason Playwright tests are less flaky than old Selenium tests.

### 8.3 Page Object Model (POM)
Each screen is a class (`DashboardPage`, `NewApplicationPage`, `ApplicationDetailPage`) that owns its
locators and actions. Tests read like a story:

```python
form.fill(data); form.submit()
detail.review("J. Rowe", "Verified two recent pay stubs", approve=True)
expect(detail.status).to_have_text("APPROVED")
```

### 8.4 Arrange by API, act by UI, assert both
`test_apply_refer_then_underwriter_approves` drives the browser, then checks the saved record through
the API. A UI can show "APPROVED" while the database says otherwise; checking both catches it.
Setting up data through the API (`referred_application` fixture) keeps UI tests fast.

### 8.5 When a UI test fails
`qe.py` runs UI suites with `--screenshot=only-on-failure --tracing=retain-on-failure`. Open the trace:

```powershell
.\.venv\Scripts\playwright show-trace reports\playwright\<test-folder>\trace.zip
```

It's a recording of every step, with DOM snapshots, network calls and console output. You can see
exactly what the page looked like at the moment of failure.

### 8.6 Small but sharp checks
- **XSS:** `test_script_in_applicant_name_is_shown_as_text_not_run` saves a name containing
  `<img src=x onerror=alert('xss')>` and checks the page shows it as text and no dialog opens
  (`browser_problems` fixture).
- **Keyboard-only:** `test_form_can_be_completed_with_the_keyboard_only` tabs through the form and
  submits with Enter.
- **Stats reconcile:** the dashboard tiles must equal `/api/stats`. It's the same idea as balancing a
  till: two records of the same thing must agree.

---

## Part 9. Service virtualization with WireMock

The posting asks you to "leverage virtual assets to support virtualization of any incomplete or
unavailable code, service, database". This is that.

### 9.1 Why
In a bank, the service your screen depends on may be unfinished, owned by another team, down for
maintenance, or impossible to push into a rare state on demand (a 500 error, a 3-second delay, a
reason code today's rules never produce). A **virtual service** pretends to be it, with answers you
control. UI work and testing don't have to wait.

### 9.2 How it is set up here
- `virtualization/mappings/*.json`: **stubs**. "When `GET /api/stats` arrives, answer with
  `__files/stats.json`." Each has `priority: 10`.
- `virtualization/__files/*.json`: the response bodies (3 fictional applications, one per status).
- `{{request.headers.X-Correlation-Id}}` uses response templating to echo the caller's header.
- `qe.py virtual start` runs WireMock on 8089 and a UI copy on 4401 pointing at it.

### 9.3 Per-test overrides
```python
wiremock.stub("GET", "/api/applications", 500, INTERNAL_ERROR)          # priority 1 beats 10
wiremock.stub("GET", "/api/applications", 200, empty_page, delay_ms=2500)
```
`framework/wiremock.py` posts a temporary stub through WireMock's admin API (`/__admin/mappings`).
The `wiremock` fixture calls `reset()` before and after each test, which restores the file stubs, so
tests never leak into each other.

### 9.4 What the virtual suite proves (CL-NFR04, resilience)
| Situation | Expected UI behaviour |
|---|---|
| API returns 500 | safe message with the support reference, no stack trace |
| API unreachable (Playwright `route.abort`) | "Cannot reach the API ..." |
| API takes 2.5 s | "Loading..." then the data |
| Server rejects a field the UI thought was fine | the server's message appears next to that field; user can retry |
| 409 during review | explanation shown, status unchanged |
| All nine reason codes at once | every code renders with the right severity colour |
| Typing fast in the form | the preview is debounced (1-2 calls, not 6), checked with WireMock's request journal |

### 9.5 Keep virtual assets honest
A stub that drifts from the real API makes tests pass against something that doesn't exist.
`test_virtual_stub_matches_contract` validates every stub body against the same JSON Schemas as the
real API. If the real contract changes, the stubs fail too.

---

## Part 10. Accessibility testing

Ontario's AODA requires public websites of large organizations to meet **WCAG 2.0 level AA**, and banks generally aim for **WCAG 2.1 AA**.
`framework/axe.py` injects **axe-core** (the engine inside Chrome Lighthouse and many enterprise
tools) and runs the WCAG 2.0/2.1 A and AA rules. Serious or critical findings fail the test. The full
results are saved to `reports/a11y/*.json`.

Screens and *states* are scanned: dashboard, the form with its preview, the form showing errors, and
the review screen. Error states often hide problems such as low-contrast red text or errors that
aren't tied to their field.

**DEF-002 (found by axe):** the header logo link has `aria-label="CreditLens home"`, but its visible
text is "CreditLens Credit Decisions". A voice-control user who says "click CreditLens Credit Decisions"
gets nothing (WCAG 2.5.3, Label in Name). It's logged, listed in `KNOWN_ISSUES` so it doesn't block
other screens, and has its own strict-xfail test.

**Automated tools find roughly a third to a half of accessibility issues.** A QE also does manual
checks: keyboard-only use (one is automated here), a screen reader (NVDA is free on Windows), zoom to
200%, and colour-only meaning.

---

## Part 11. Security testing basics

`tests/security/test_api_security.py`. None of this replaces a penetration test; it's the
automatable baseline every build should pass.

| Check | Why |
|---|---|
| `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Cache-Control: no-store` on every `/api` response, errors included | stops MIME sniffing, clickjacking and caching of financial data |
| Weird bodies (`1e999`, `[]`, `{"$gt":0}`, binary) → no 500s, no `Exception` / `springframework` / `SQL` in the response | error messages must not leak internals to an attacker |
| Bad `X-Correlation-Id` values (CRLF, too short, `<script>`) are replaced | **log injection**: a newline in a logged header can forge log lines |
| CORS preflight from `https://evil.example` gets 403 and no allow-origin header | only the real front end may call the API from a browser |
| `' OR '1'='1`, `DROP TABLE`, `<img onerror>` saved as names come back unchanged and the DB still answers | SQL injection prevented by parameterized queries, output encoding in the UI |
| PUT / DELETE / PATCH refused | nothing outside the contract is reachable |
| Email masked in every response (`t************@example.com`) | PII protection |

The CI pipeline adds an **OWASP ZAP baseline** scan (`zap` job): ZAP crawls the running app and
passively reports issues such as a missing Content-Security-Policy. `.zap/rules.tsv` records which
findings are warnings and which are accepted, with the reason for each.

**Gap to raise as a QE:** CreditLens has no authentication, so anyone can review an application.
That goes in the test plan's risks section rather than being quietly ignored.

---

## Part 12. Performance testing

`perf/locustfile.py` describes a **load model**: who uses the system and how. Applicants preview six
times for every submit; underwriters refresh the dashboard. Locust simulates 20 such users for 30
seconds. `tests/perf/test_load.py` turns the results into pass/fail checks against
`perf/thresholds.json`:

- error ratio 0%
- **p95** latency: preview ≤ 300 ms, submit ≤ 500 ms, list ≤ 400 ms, stats ≤ 300 ms

**Why p95 and not the average:** an average hides the slow tail. If 19 calls take 50 ms and 1 takes
3 seconds, the average looks fine (~200 ms) and one customer in twenty is frustrated. p95 means 95% of
requests were at least this fast.

**Kinds of performance test:**
| Type | Question |
|---|---|
| Load | Does it meet the SLO at expected peak traffic? (this repo) |
| Stress | Where does it break, and does it fail gracefully? |
| Spike | What happens when traffic jumps 10× in seconds (payday, a promo)? |
| Soak / endurance | Does it degrade over hours (memory leaks, connection pools)? |

**ORT (operational readiness testing)** asks whether the system can be run in production: is it
monitorable, does it report health, can support trace a failure? The smoke suite's checks
(`/actuator/health`, Prometheus metrics, correlation ids on every response) are small ORT checks.

Try the Locust web UI: `.\.venv\Scripts\locust -f perf\locustfile.py --host http://localhost:8080`,
then open http://localhost:8089. Stop WireMock first: it uses the same port.

---

## Part 13. Traceability and defect management

### Traceability matrix
`reports/traceability.html` lists each requirement, its acceptance criteria, every test that proves
it, and a status: PASSING, FAILING, KNOWN DEFECT, NOT RUN or **NOT COVERED**. NOT COVERED is the most
important one, because it shows a gap before an auditor finds it. In regulated work (OSFI-supervised
banks) you must be able to show which tests prove which requirement. The CSV version opens in Excel.

How it works: tests carry `@pytest.mark.req("CL-US11")` (Gherkin: `@req:CL-US11`); the plugin rejects
ids that aren't in `requirements.json`, collects outcomes, and merges results from separate suite runs.

### Defects
`docs/DEFECTS.md` follows the standard shape: summary, component, environment, steps to reproduce,
expected, actual, evidence, severity, priority, suggested fix.

- **Severity** = how bad the impact is. **Priority** = how soon it should be fixed. They differ: a
  misspelled bank name on the login page is low severity but high priority.
- **Lifecycle:** New → Triaged → In progress → Fixed → Retest → Closed (or Reopened).
- Every open defect has a strict-xfail test, so the fix is verified automatically on retest.

---

## Part 14. CI/CD/CT: the pipeline

`.github/workflows/qe.yml` runs on every push and pull request, on a weekday schedule, and on demand.

1. Check out **two repos**: this framework and the system under test (`jamierowe15/creditlens`).
2. Set up Java 21, Node 24, Python 3.12, with dependency caching.
3. Install the pinned test tools and Playwright's Chromium.
4. `python qe.py all`: build, start, run every suite. **Smoke gates the run**: if the app isn't healthy,
   it stops instead of reporting 270 confusing failures.
5. Publish the summary table on the run page and upload `reports/` as an artifact (HTML reports,
   JUnit XML, traceability, Playwright traces, perf report).
6. A parallel `zap` job runs the OWASP ZAP baseline scan.

**CI/CD/CT:** continuous integration (every change builds), continuous delivery (every green build
could ship), and continuous testing (the tests are part of that path, not a phase after it).

**Next step you could add:** trigger this workflow from the CreditLens repo on every CreditLens
pull request (a `repository_dispatch` event), so a developer's change is tested before it merges.

---

## Part 15. Exercises: make it yours

Do these yourself. Each one is a realistic first-month task, and each gives you something to say in
an interview.

1. **New rule.** The product owner adds "requests over $75,000 with a term under 24 months refer". Add
   it to `requirements.json` (CL-US16), write the boundary tests first (they fail, which is TDD), then
   add the rule to CreditLens and watch them go green.
2. **Fix DEF-002** in CreditLens' `app.ts`. Re-run `qe.py test a11y`: the strict-xfail test now
   *XPASSes* and fails the run. Remove the xfail and the `KNOWN_ISSUES` entry, then close the defect.
3. **New virtual scenario.** Stub `/api/stats` to answer in 4 seconds and decide what the dashboard
   *should* do. Is the missing loading state for the tiles a defect? Log it if so.
4. **Stress test.** Copy `thresholds.json`, raise users to 200, find where p95 breaks the SLO, and write
   two sentences on what you'd tell the team.
5. **PostgreSQL run.** Start CreditLens with the `postgres` profile (`docker compose up -d`) and run the
   API suite against it. Note any difference from H2.
6. **Read a trace.** Break a locator on purpose, run `qe.py test ui`, open the trace and find the
   failing step. Then put it back.

---

## Part 16. Interview preparation

### Your two-minute story
"I built CreditLens, a credit decisioning app in Spring Boot and Angular. Then I tested it the way a
QE team would. I wrote the requirements as user stories with acceptance criteria and built a Python
framework around them: API and contract tests with JSON Schema, boundary-value and model-based tests
of the credit rules against an independent oracle, BDD scenarios in Gherkin, Playwright UI tests with
page objects, WireMock virtual services for failure cases, axe-core accessibility scans, Locust load
tests with p95 SLOs, and an OWASP ZAP scan. It all runs in GitHub Actions and produces a traceability
matrix. It found two real defects: a rounding issue that let loans a few dollars over the
loan-to-income limit through, and a WCAG 2.5.3 problem on the header link. I logged both with root
causes and suggested fixes."

### Likely questions

**How do you decide what to automate?** Stable, repeated, high-risk checks first: the credit rules
(regulatory, many cases), the API contract (many consumers), the critical journey (apply → refer →
review). Exploratory testing and one-off visual checks stay manual. Most tests sit at the API level
because they're fast and precise, with a few UI journeys on top (the test pyramid).

**How do you handle flaky UI tests?** Find the cause instead of adding retries. Usually it's a fixed
sleep, a fragile CSS selector, or shared data. I use role and label locators, Playwright's
auto-waiting `expect`, data created per test through the API, and traces on failure to diagnose.

**What is service virtualization and when would you use it?** Replacing a dependency with a
controllable fake. Use it when the real service is unfinished, unstable, shared, costly, or can't
produce the state you need. In my project WireMock simulates 500s, timeouts, 409 conflicts and rare
data, and I validate the stubs against the real contract so they can't drift.

**Explain the difference between severity and priority.** Severity is impact; priority is urgency.
Give the login-typo example.

**What would you test first on a new feature?** Read the story, then agree testable acceptance
criteria with the PO and developer (DoR). Find the boundaries and state transitions. Ask about test
data and environments early. Then automate at the lowest level that can prove each criterion.

**Tell me about a defect you found.** DEF-001: technique (BVA, one step above the line) → result
(approved) → root cause (rounding before comparison in `LoanMath.ratio`) → impact (small, but a
regulated control) → fix options → strict-xfail test to verify the fix.

**Why Python for a Java app?** The tests talk to the system through HTTP and the browser, so the
language is independent of the app's. Python made it fast to write. In a Java shop I'd use the same
design with REST Assured, Cucumber-JVM and Playwright for Java.

**How do you measure quality?** Pass rate per suite, requirements coverage (no NOT COVERED), defect
counts by severity and how long they stay open, escaped defects (bugs found in production), and
performance against SLOs over time.

Be ready to say plainly that this is a portfolio lab, not production experience, and that you're
happy to do a technical assessment.

---

## Glossary

| Term | Meaning |
|---|---|
| SUT | System under test (CreditLens) |
| Fixture | pytest setup function a test asks for by name |
| Oracle | Anything that tells you the correct expected result |
| Contract test | Checks the shape and rules of an API's responses |
| BVA / EP | Boundary-value analysis / equivalence partitioning |
| POM | Page Object Model: one class per screen |
| Stub / mock / virtual service | A fake dependency that answers in a controlled way |
| xfail (strict) | Expected failure for a known defect; strict fails the run if it starts passing |
| p95 | 95th percentile latency: 95% of requests were this fast or faster |
| SLO | Service level objective: the target (for example, p95 ≤ 300 ms) |
| ORT | Operational readiness testing: can it be run, monitored and supported? |
| WCAG | Web Content Accessibility Guidelines (2.1 AA is the usual target) |
| CORS | Browser rule for which websites may call an API |
| RFC 9457 | Standard JSON format for API error responses ("problem details") |
| DoR / DoD | Definition of Ready / Definition of Done |
| CI/CD/CT | Continuous integration / delivery / testing |
| Shift-left | Testing earlier in delivery, starting at the requirements |
