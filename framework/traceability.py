"""Traceability matrix plugin.

Tag a test with the requirement(s) it proves:

    @pytest.mark.req("CL-US03")
    def test_score_599_declines(...): ...

BDD scenarios are tagged in the .feature file instead:  @req:CL-US03

At the end of every run this plugin writes reports/traceability.html and .csv:
requirement -> tests -> pass/fail, plus a list of requirements with NO tests (a coverage gap).
Results from separate runs (api, ui, perf...) are merged, so the final matrix covers everything.
"""
from __future__ import annotations

import csv
import html
import json
from collections import defaultdict
from datetime import datetime

import pytest

from config.settings import REPORTS, ROOT

_RESULTS_FILE = REPORTS / "trace-results.json"


def _load_requirements() -> list[dict]:
    return json.loads((ROOT / "requirements" / "requirements.json").read_text(encoding="utf-8"))["requirements"]


def _reqs_of(item: pytest.Item) -> list[str]:
    ids: list[str] = []
    for mark in item.iter_markers(name="req"):
        ids.extend(mark.args)
    # pytest-bdd turns a Gherkin tag "@req:CL-US03" into a marker named "req:CL-US03"
    for mark in item.iter_markers():
        if mark.name.startswith("req:"):
            ids.append(mark.name.split(":", 1)[1])
    return sorted(set(ids))


class TraceabilityPlugin:
    def __init__(self) -> None:
        self.known = {r["id"] for r in _load_requirements()}
        self.outcomes: dict[str, dict] = {}

    @pytest.hookimpl(tryfirst=True)
    def pytest_collection_modifyitems(self, config, items):
        unknown = {(i.nodeid, r) for i in items for r in _reqs_of(i) if r not in self.known}
        if unknown:
            lines = "\n".join(f"  {n} -> {r}" for n, r in sorted(unknown))
            raise pytest.UsageError(f"Tests reference requirement ids that are not in requirements.json:\n{lines}")

    def pytest_runtest_logreport(self, report):
        item_reqs = getattr(report, "_qe_reqs", None)
        if item_reqs is None:
            return
        entry = self.outcomes.setdefault(report.nodeid, {"reqs": [], "outcome": "passed"})
        entry["reqs"] = sorted(set(entry["reqs"]) | set(item_reqs))
        if report.when == "call" and hasattr(report, "wasxfail"):
            entry["outcome"] = "xfailed" if report.skipped else "xpassed"
        elif report.failed:
            entry["outcome"] = "failed"
        elif report.skipped and entry["outcome"] == "passed":
            entry["outcome"] = "skipped"

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item, call):
        outcome = yield
        outcome.get_result()._qe_reqs = _reqs_of(item)

    def pytest_sessionfinish(self, session):
        if not self.outcomes:
            return
        REPORTS.mkdir(exist_ok=True)
        merged = json.loads(_RESULTS_FILE.read_text(encoding="utf-8")) if _RESULTS_FILE.exists() else {}
        merged.update(self.outcomes)
        _RESULTS_FILE.write_text(json.dumps(merged, indent=1), encoding="utf-8")
        write_matrix(merged)


def write_matrix(results: dict | None = None) -> None:
    if results is None:
        results = json.loads(_RESULTS_FILE.read_text(encoding="utf-8")) if _RESULTS_FILE.exists() else {}
    reqs = _load_requirements()
    by_req: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for nodeid, r in results.items():
        for rid in r["reqs"]:
            by_req[rid].append((nodeid, r["outcome"]))

    def status(tests):
        if not tests:
            return "NOT COVERED"
        outs = {o for _, o in tests}
        if "failed" in outs:
            return "FAILING"
        if "xfailed" in outs:
            return "KNOWN DEFECT"
        if outs <= {"skipped"}:
            return "NOT RUN"
        return "PASSING"

    REPORTS.mkdir(exist_ok=True)
    with open(REPORTS / "traceability.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["requirement", "title", "status", "tests", "passed", "failed", "known_defects", "test_ids"])
        for r in reqs:
            t = by_req.get(r["id"], [])
            w.writerow([r["id"], r["title"], status(t), len(t), sum(o == "passed" for _, o in t),
                        sum(o == "failed" for _, o in t), sum(o == "xfailed" for _, o in t), " | ".join(n for n, _ in t)])

    colors = {"PASSING": "#1e7b34", "FAILING": "#b3261e", "KNOWN DEFECT": "#8a5a00", "NOT COVERED": "#6b6b6b", "NOT RUN": "#6b6b6b"}
    rows = []
    for r in reqs:
        t = by_req.get(r["id"], [])
        s = status(t)
        crit = "".join(f"<li>{html.escape(a)}</li>" for a in r.get("acceptance", []))
        tests = "".join(f"<li class='{o}'>{html.escape(n)} <b>{o}</b></li>" for n, o in sorted(t))
        rows.append(f"<tr><td><b>{r['id']}</b><br><small>{r['type']}</small></td><td>{html.escape(r['title'])}<ul>{crit}</ul></td>"
                    f"<td style='color:{colors[s]};font-weight:700'>{s}</td><td>{len(t)}</td><td><ul class='t'>{tests}</ul></td></tr>")
    covered = sum(1 for r in reqs if by_req.get(r["id"]))
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>CreditLens traceability matrix</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;margin:24px;color:#1b1b1b}}table{{border-collapse:collapse;width:100%}}
td,th{{border:1px solid #ccc;padding:6px 8px;vertical-align:top;text-align:left;font-size:13px}}th{{background:#1F3864;color:#fff}}
ul{{margin:4px 0;padding-left:18px}}ul.t li{{font-family:Consolas,monospace;font-size:11.5px;word-break:break-all}}table{{table-layout:fixed}}li.failed b{{color:#b3261e}}li.passed b{{color:#1e7b34}}li.xfailed b{{color:#8a5a00}}</style></head>
<body><h1>CreditLens requirements traceability matrix</h1>
<p>Generated {datetime.now():%Y-%m-%d %H:%M}. {covered} of {len(reqs)} requirements have automated tests. {len(results)} test results.</p>
<table><colgroup><col style='width:90px'><col style='width:30%'><col style='width:110px'><col style='width:40px'><col></colgroup><tr><th>ID</th><th>Requirement and acceptance criteria</th><th>Status</th><th>#</th><th>Tests</th></tr>{''.join(rows)}</table></body></html>"""
    (REPORTS / "traceability.html").write_text(doc, encoding="utf-8")
