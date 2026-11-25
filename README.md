# CreditLens QE: test automation framework

![QE](https://github.com/jamierowe15/creditlens-qe/actions/workflows/qe.yml/badge.svg)

A quality engineering framework for **[CreditLens](https://github.com/jamierowe15/creditlens)**, my
Spring Boot + Angular credit decisioning app. It tests the app the way a bank's QE team would:
functional and non-functional, real and virtualized, traced to requirements, and run automatically
in a CI/CD pipeline on every change.

**278 automated tests across 8 suites. They found 2 real defects in CreditLens** ([defect log](docs/DEFECTS.md)).

| Suite | What it proves | Tools |
|---|---|---|
| `smoke` | The system is up and observable (gates the pipeline) | pytest, requests |
| `api` | REST contract, every credit rule at its boundaries, 100 model-based cases vs an independent oracle, validation, underwriter state machine, audit trail, concurrency | pytest, JSON Schema |
| `bdd` | The policy in plain English that a business analyst can read and extend | pytest-bdd (Gherkin) |
| `security` | OWASP secure headers, no stack-trace leakage, CORS, SQL/script injection, log injection | pytest + OWASP ZAP baseline in CI |
| `ui` | Real browser journeys: apply, live preview, underwriter review, filters, paging, XSS, keyboard-only | Playwright, Page Object Model |
| `virtual` | UI behaviour when the API fails, is slow, conflicts or returns rare data | WireMock service virtualization |
| `a11y` | WCAG 2.1 AA on every screen and error state | axe-core |
| `perf` | p95 latency and error-rate SLOs at 20 concurrent users | Locust |

Every test is tagged with a requirement id, and each run produces a
**requirements traceability matrix** (`reports/traceability.html`), which flags any requirement with no test.

## Run it (Windows)

Put this folder next to your `creditlens` clone, then:

```powershell
powershell -ExecutionPolicy Bypass -File .\Setup-CreditLensQE.ps1
```

The script installs anything missing, builds and starts CreditLens and WireMock, runs every suite
and opens the report. Options: `-Headed` (watch the browser), `-Suite api`, `-SetupOnly`, `-Publish`.

Day to day:

```powershell
.\.venv\Scripts\python qe.py all              # whole pipeline, then stops the servers
.\.venv\Scripts\python qe.py sut start        # start CreditLens (API :8080, UI :4400)
.\.venv\Scripts\python qe.py test api         # run one suite
.\.venv\Scripts\python qe.py test ui --headed # watch it
.\.venv\Scripts\python qe.py doctor           # what's installed, what's running
```

## Layout

```
qe.py                     command centre: environments, suites, reports
config/settings.py        URLs and paths (all overridable with environment variables)
framework/                API client, JSON-schema checker, WireMock client, axe helper,
                          traceability plugin, page objects (framework/pages)
testdata/                 builders + personas (test data management), oracle (expected results)
requirements/             user stories + NFRs with acceptance criteria (traceability source)
schemas/                  JSON Schema contracts for every response
tests/api|bdd|security|ui|virtual|a11y|perf
virtualization/           WireMock mappings and response bodies (the virtual CreditLens)
perf/                     Locust load model + SLO thresholds
docs/                     TEST_PLAN.md, DEFECTS.md, LECTURE.md (how and why everything works)
.github/workflows/qe.yml  CI pipeline: build CreditLens, run all suites, ZAP scan, publish reports
```

## Reports (`reports/`)

`index.html` summary · `<suite>.html` details · `junit-*.xml` for CI · `traceability.html/.csv` ·
`perf/load-report.html` · `a11y/*.json` · Playwright traces and screenshots for any failed UI test
(open with `.venv\Scripts\playwright show-trace <file>`).

All data is fictional. Portfolio project, not affiliated with any bank.
