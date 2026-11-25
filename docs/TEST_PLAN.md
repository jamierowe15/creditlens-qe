# Test plan: CreditLens credit decisioning platform

| | |
|---|---|
| System under test | CreditLens (github.com/jamierowe15/creditlens): Spring Boot 3.5 API, Angular 22 UI, H2/PostgreSQL |
| Rules version | 2026.11-v1 |
| Test framework | creditlens-qe (this repo) |
| Author | Jamie Rowe |

## 1. Objectives
1. Prove every credit rule decides correctly at its exact boundaries, with the right reason codes.
2. Prove the REST contract the UI depends on (status codes, JSON shapes, RFC 9457 errors).
3. Prove the underwriter workflow and audit trail behave as a controlled state machine.
4. Prove the non-functional requirements: security basics, performance SLOs, WCAG 2.1 AA, resilience.
5. Run all of it automatically on every change (CI/CD/CT) and trace every result to a requirement.

## 2. Scope
**In scope:** all endpoints under `/api`, actuator health/metrics, the three Angular screens
(dashboard, new application, application detail), the decision policy, pricing and payment math.
**Out of scope:** PostgreSQL-specific behaviour (covered by CreditLens' own Flyway/integration tests),
browser compatibility beyond Chromium, authentication (CreditLens has none yet; noted as a risk).

## 3. Approach: the test pyramid

| Level | Where | Tool | Owner |
|---|---|---|---|
| Unit (engine, LoanMath) | CreditLens repo, `mvn verify` | JUnit 5, AssertJ | developers |
| API + contract | `tests/api`, `schemas/` | pytest, requests, JSON Schema | QE |
| Business-readable scenarios | `tests/bdd/features` | pytest-bdd (Gherkin) | QE + business |
| Security | `tests/security`, ZAP job in CI | pytest, OWASP ZAP baseline | QE |
| UI end-to-end | `tests/ui` | Playwright, Page Object Model | QE |
| UI against virtual services | `tests/virtual`, `virtualization/` | WireMock + Playwright | QE |
| Accessibility | `tests/a11y` | axe-core | QE |
| Performance | `perf/`, `tests/perf` | Locust | QE |

Most tests sit at the API level: fast, stable, precise. UI tests cover the journeys a person
actually takes, not every rule again.

### Test design techniques used
- **Boundary-value analysis**: 599/600, 659/660, DTI 40.00/40.01/50.00/50.01%, LTI 50%/100%, income $19,999.99/$20,000.
- **Equivalence partitioning**: one invalid value per field per partition (`test_api_validation.py`).
- **State-transition testing**: REFERRED is the only state that may change; every other transition must give 409.
- **Model-based testing**: 100 seeded random profiles compared with an independent oracle (`testdata/oracle.py`).
- **Decision tables**: worst-outcome-wins combinations (`decline-beats-refer`, `all-refers-reported`).
- **Fault injection**: 500s, 409s, 3-second delays and network failures through WireMock and Playwright routing.

## 4. Test data management
- `testdata/builders.py`: builder pattern starting from a profile that passes every rule, so each test changes one thing.
- Named personas shared by BDD, UI and humans ("near-prime borrower", "thin-file student" ...).
- Generated data uses a fixed seed: the same "random" cases every run, so failures reproduce.
- Every test-created applicant uses a `qe.` email at example.com: easy to find, never deliverable.
- Virtual data in `virtualization/__files` is itself contract-tested so the stubs cannot drift from the real API.

## 5. Environments
| Name | API | UI | Used by |
|---|---|---|---|
| Real | CreditLens jar, port 8080 | built Angular app via `tools/spa_proxy.py`, port 4400 | smoke, api, bdd, security, ui, a11y, perf |
| Virtual | WireMock, port 8089 | the same build, port 4401 | virtual |

`python qe.py sut start` and `python qe.py virtual start` create them; `python qe.py all` does everything.

## 6. Entry and exit criteria
**Entry:** CreditLens builds and its own unit tests pass; `/actuator/health` reports UP (the smoke suite gates the run).
**Exit (release ready):**
- 0 failed tests in every suite.
- Every requirement in `requirements/requirements.json` is PASSING or KNOWN DEFECT in the traceability matrix; none NOT COVERED.
- No open Critical/High defects. Medium defects have an agreed fix date.
- Perf SLOs met: preview p95 ≤ 300 ms, submit p95 ≤ 500 ms, 0% errors at 20 users.
- No serious/critical axe violations other than logged defects.

## 7. Defect management
Logged in `docs/DEFECTS.md` with steps, expected vs actual, evidence and suggested fix. Each open defect
has a strict-xfail test so the pipeline stays green but cannot forget it.

## 8. Risks
| Risk | Mitigation |
|---|---|
| No authentication or roles in CreditLens: anyone can review | Flagged to the product owner; RBAC tests to be added once auth exists |
| H2 in tests behaves differently from PostgreSQL | CreditLens has a `postgres` profile; add a nightly run against it |
| UI tests become flaky | Role/label locators, auto-waiting `expect`, no fixed sleeps, Playwright traces kept on failure |
| Shared environment data changes under the tests | Each test creates its own data through builders; assertions avoid global totals except where reconciled |

## 9. Reporting
`reports/index.html` (suite summary), `reports/<suite>.html` (details), `reports/junit-*.xml` (CI),
`reports/traceability.html|csv`, `reports/perf/load-report.html`, `reports/a11y/*.json`, Playwright traces for failures.
