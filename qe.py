#!/usr/bin/env python3
"""CreditLens QE command centre. One entry point for starting environments and running suites.

    python qe.py doctor                 check tools, folders and ports
    python qe.py sut start|stop|status  the REAL system: CreditLens API (8080) + UI (4400)
    python qe.py virtual start|stop     the VIRTUAL system: WireMock (8089) + UI (4401)
    python qe.py test <suite> [--headed]
                                        suites: smoke api bdd security ui virtual a11y perf
    python qe.py all [--headed]         start everything, run every suite in pipeline order,
                                        write reports/index.html, stop what it started
    python qe.py report                 rebuild reports/index.html from the last results

Works the same on Windows and Linux (GitHub Actions)."""
from __future__ import annotations

import argparse
import html
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import requests

from config import settings

ROOT = settings.ROOT
STATE = ROOT / ".qe"
PIDS = STATE / "pids.json"
LOGS = settings.REPORTS / "logs"
IS_WIN = os.name == "nt"
if IS_WIN:
    os.system("")  # switch the Windows console into ANSI mode so the colours render

SUITES = {
    # name: (pytest args, needs real SUT, needs virtual env, description)
    "smoke":    (["tests", "-m", "smoke"], True, False, "Is it alive? API health, metrics, dashboard loads"),
    "api":      (["tests/api"], True, False, "REST contract, decision rules, validation, workflow"),
    "bdd":      (["tests/bdd"], True, False, "Gherkin scenarios in business language"),
    "security": (["tests/security"], True, False, "Headers, error leakage, CORS, injection, log injection"),
    "ui":       (["tests/ui"], True, False, "Browser end-to-end on the real stack (Playwright)"),
    "virtual":  (["tests/virtual"], False, True, "UI against WireMock: errors, delays, edge cases"),
    "a11y":     (["tests/a11y"], True, False, "WCAG 2.1 AA scans with axe-core"),
    "perf":     (["tests/perf"], True, False, "Locust load test with p95 / error-rate SLOs"),
}
PIPELINE = ["smoke", "api", "bdd", "security", "ui", "virtual", "a11y", "perf"]


# ------------------------------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------------------------------
def say(msg: str, color: str = "36") -> None:
    print(f"\033[{color}m{msg}\033[0m" if sys.stdout.isatty() else msg, flush=True)


def tool(name: str) -> str | None:
    override = os.environ.get(f"QE_{name.upper()}")
    return override or shutil.which(name)


def up(url: str) -> bool:
    try:
        return requests.get(url, timeout=3).status_code < 500
    except requests.RequestException:
        return False


def health_up() -> bool:
    try:
        return requests.get(f"{settings.API_URL}/actuator/health", timeout=3).json().get("status") == "UP"
    except Exception:
        return False


def wait_for(check, what: str, seconds: int) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if check():
            say(f"  {what} is up")
            return
        time.sleep(2)
    raise SystemExit(f"{what} did not come up within {seconds}s. See logs in {LOGS}")


def load_pids() -> dict:
    return json.loads(PIDS.read_text()) if PIDS.exists() else {}


def save_pids(p: dict) -> None:
    STATE.mkdir(exist_ok=True)
    PIDS.write_text(json.dumps(p, indent=1))


def spawn(name: str, cmd: list[str], cwd: Path | None = None) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    log = open(LOGS / f"{name}.log", "w", encoding="utf-8")
    kwargs = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if IS_WIN else {"start_new_session": True}
    proc = subprocess.Popen(cmd, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, **kwargs)
    pids = load_pids()
    pids[name] = proc.pid
    save_pids(pids)
    say(f"  started {name} (pid {proc.pid}) -> reports/logs/{name}.log")


def kill(name: str) -> None:
    pids = load_pids()
    pid = pids.pop(name, None)
    save_pids(pids)
    if not pid:
        return
    try:
        if IS_WIN:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        else:
            os.killpg(pid, signal.SIGTERM)
        say(f"  stopped {name}")
    except (ProcessLookupError, PermissionError):
        pass


def run(cmd: list[str], cwd: Path) -> None:
    say(f"  $ {' '.join(cmd)}   (in {cwd})", "90")
    subprocess.run(cmd, cwd=cwd, check=True)


# ------------------------------------------------------------------------------------------
# environments
# ------------------------------------------------------------------------------------------
def portable_maven() -> str | None:
    """Maven unzipped into .tools/ by the setup script (no system-wide install needed)."""
    for m in sorted((ROOT / ".tools").glob("apache-maven-*/bin/" + ("mvn.cmd" if IS_WIN else "mvn")), reverse=True):
        return str(m)
    return None


def frontend_dist() -> Path:
    fe = settings.SUT_DIR / "frontend"
    dist = fe / "dist" / "frontend" / "browser"
    if not (dist / "index.html").exists():
        npm = tool("npm") or sys.exit("npm not found on PATH")
        say("Building the CreditLens Angular app (first run only)...")
        run([npm, "install", "--no-audit", "--no-fund"], fe)
        run([npm, "run", "build"], fe)
    return dist


def backend_jar() -> Path:
    be = settings.SUT_DIR / "backend"
    jars = sorted((be / "target").glob("creditlens-api-*.jar"))
    jars = [j for j in jars if not j.name.endswith(("-plain.jar", "-sources.jar"))]
    if not jars:
        mvn = os.environ.get("CREDITLENS_MVN") or tool("mvn") or portable_maven() or sys.exit("Maven (mvn) not found on PATH")
        say("Building the CreditLens API jar (first run only, a few minutes)...")
        run([mvn, "-B", "-q", "-DskipTests", "package"], be)
        jars = sorted((be / "target").glob("creditlens-api-*.jar"))
    return jars[0]


def sut_start() -> list[str]:
    started = []
    if not settings.SUT_DIR.exists():
        sys.exit(f"CreditLens repo not found at {settings.SUT_DIR}. Clone it next to this folder or set QE_SUT_DIR.")
    say("Real system under test")
    if health_up():
        say(f"  API already running at {settings.API_URL} (reusing it)")
    else:
        java = tool("java") or sys.exit("java not found on PATH (JDK 21 needed)")
        spawn("creditlens-api", [java, "-jar", str(backend_jar())])
        started.append("creditlens-api")
        wait_for(health_up, "CreditLens API", 240)
    if up(settings.UI_URL):
        say(f"  UI already running at {settings.UI_URL}")
    else:
        spawn("ui-real", [sys.executable, str(ROOT / "tools" / "spa_proxy.py"), "--dist", str(frontend_dist()),
                          "--port", settings.UI_URL.rsplit(":", 1)[1], "--api", settings.API_URL])
        started.append("ui-real")
        wait_for(lambda: up(settings.UI_URL), "CreditLens UI", 30)
    return started


def virtual_start() -> list[str]:
    started = []
    say("Virtual system (service virtualization)")
    if up(f"{settings.VIRTUAL_API_URL}/__admin/mappings"):
        say(f"  WireMock already running at {settings.VIRTUAL_API_URL}")
    else:
        npx = tool("npx") or sys.exit("npx not found on PATH (Node.js needed)")
        if not (ROOT / "node_modules" / "wiremock").exists():
            run([tool("npm") or "npm", "install", "--no-audit", "--no-fund"], ROOT)
        spawn("wiremock", [npx, "wiremock", "--port", settings.VIRTUAL_API_URL.rsplit(":", 1)[1],
                           "--root-dir", str(ROOT / "virtualization"), "--global-response-templating", "--disable-banner"])
        started.append("wiremock")
        wait_for(lambda: up(f"{settings.VIRTUAL_API_URL}/__admin/mappings"), "WireMock", 90)
    if up(settings.VIRTUAL_UI_URL):
        say(f"  virtual UI already running at {settings.VIRTUAL_UI_URL}")
    else:
        spawn("ui-virtual", [sys.executable, str(ROOT / "tools" / "spa_proxy.py"), "--dist", str(frontend_dist()),
                             "--port", settings.VIRTUAL_UI_URL.rsplit(":", 1)[1], "--api", settings.VIRTUAL_API_URL])
        started.append("ui-virtual")
        wait_for(lambda: up(settings.VIRTUAL_UI_URL), "virtual UI", 30)
    return started


def stop(names) -> None:
    for n in names:
        kill(n)


# ------------------------------------------------------------------------------------------
# suites and reports
# ------------------------------------------------------------------------------------------
def run_suite(name: str, headed: bool = False) -> int:
    args, *_ , desc = SUITES[name]
    say(f"\n=== {name}: {desc}", "1;34")
    cmd = [sys.executable, "-m", "pytest", *args,
           f"--junitxml={settings.REPORTS / f'junit-{name}.xml'}",
           f"--html={settings.REPORTS / f'{name}.html'}", "--self-contained-html",
           "-o", f"junit_suite_name={name}"]
    if name in ("ui", "virtual", "a11y", "smoke"):
        cmd += ["--screenshot=only-on-failure", "--tracing=retain-on-failure", f"--output={settings.REPORTS / 'playwright'}"]
        if headed:
            cmd += ["--headed", "--slowmo=250"]
        if os.environ.get("QE_BROWSER_CHANNEL"):
            cmd += ["--browser-channel", os.environ["QE_BROWSER_CHANNEL"]]
    else:
        cmd += ["-p", "no:playwright"]
    return subprocess.run(cmd, cwd=ROOT).returncode


def junit_counts(name: str) -> dict | None:
    f = settings.REPORTS / f"junit-{name}.xml"
    if not f.exists():
        return None
    root = ET.parse(f).getroot()
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    c = {k: int(suite.get(k, 0)) for k in ("tests", "failures", "errors", "skipped")}
    c["time"] = float(suite.get("time", 0))
    xfail = sum(1 for s in suite.iter("skipped") if (s.get("type") or "").endswith("xfail"))
    c["xfailed"] = xfail
    c["skipped"] -= xfail
    c["passed"] = c["tests"] - c["failures"] - c["errors"] - c["skipped"] - xfail
    return c


def write_index(exit_codes: dict | None = None) -> Path:
    from framework.traceability import write_matrix
    write_matrix()
    rows, total = [], {"passed": 0, "failed": 0, "xfailed": 0}
    for name in PIPELINE:
        c = junit_counts(name)
        if not c:
            rows.append(f"<tr><td>{name}</td><td colspan=5 class=muted>not run</td></tr>")
            continue
        failed = c["failures"] + c["errors"]
        total["passed"] += c["passed"]; total["failed"] += failed; total["xfailed"] += c["xfailed"]
        badge = "<b class=bad>FAIL</b>" if failed else "<b class=ok>PASS</b>"
        rows.append(f"<tr><td><a href='{name}.html'>{name}</a></td><td>{badge}</td><td>{c['passed']}</td><td>{failed}</td>"
                    f"<td>{c['xfailed']}</td><td>{c['time']:.1f}s</td></tr>")
    extras = [("traceability.html", "Requirements traceability matrix"), ("traceability.csv", "Traceability (CSV for Excel)"),
              ("perf/load-report.html", "Locust load-test report"), ("a11y/", "axe-core raw results (JSON)"),
              ("../docs/DEFECTS.md", "Defect log"), ("../docs/TEST_PLAN.md", "Test plan")]
    links = "".join(f"<li><a href='{h}'>{html.escape(t)}</a></li>" for h, t in extras)
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>CreditLens QE results</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;margin:28px;color:#1b1b1b;max-width:900px}}h1{{color:#1F3864}}
table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccc;padding:7px 10px;text-align:left}}th{{background:#1F3864;color:#fff}}
.ok{{color:#1e7b34}}.bad{{color:#b3261e}}.muted{{color:#777}}.big{{font-size:20px}}</style></head><body>
<h1>CreditLens quality report</h1><p>Run {datetime.now():%Y-%m-%d %H:%M}. System under test: <code>{html.escape(str(settings.SUT_DIR))}</code></p>
<p class=big><b class=ok>{total['passed']} passed</b> &middot; <b class=bad>{total['failed']} failed</b> &middot; {total['xfailed']} known defects (xfail)</p>
<table><tr><th>Suite</th><th>Result</th><th>Passed</th><th>Failed</th><th>Known defects</th><th>Time</th></tr>{''.join(rows)}</table>
<h2>More</h2><ul>{links}</ul></body></html>"""
    out = settings.REPORTS / "index.html"
    out.write_text(doc, encoding="utf-8")
    # Markdown twin for the GitHub Actions run summary page
    md = ["## CreditLens QE results", "",
          f"**{total['passed']} passed, {total['failed']} failed, {total['xfailed']} known defects (xfail)**", "",
          "| Suite | Result | Passed | Failed | Known defects |", "|---|---|---|---|---|"]
    for name in PIPELINE:
        c = junit_counts(name)
        if c:
            failed = c["failures"] + c["errors"]
            md.append(f"| {name} | {'FAIL' if failed else 'PASS'} | {c['passed']} | {failed} | {c['xfailed']} |")
    (settings.REPORTS / "summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return out


def doctor() -> int:
    ok = True
    say("Tools")
    for t in ("python", "java", "mvn", "node", "npm", "npx", "git"):
        path = sys.executable if t == "python" else (tool(t) or (portable_maven() if t == "mvn" else None))
        say(f"  {'OK ' if path else 'MISSING'} {t:7} {path or ''}", "32" if path else "31")
        ok &= bool(path) or t in ("mvn",)
    say("Folders")
    for p, what in ((settings.SUT_DIR, "CreditLens repo"), (ROOT / "node_modules" / "wiremock", "WireMock (npm install)"),
                    (ROOT / "node_modules" / "axe-core", "axe-core (npm install)")):
        say(f"  {'OK ' if p.exists() else 'MISSING'} {what}: {p}", "32" if p.exists() else "31")
        ok &= p.exists()
    say("Services")
    for url, what in ((f"{settings.API_URL}/actuator/health", "CreditLens API"), (settings.UI_URL, "UI (real)"),
                      (f"{settings.VIRTUAL_API_URL}/__admin/mappings", "WireMock"), (settings.VIRTUAL_UI_URL, "UI (virtual)")):
        say(f"  {'UP  ' if up(url) else 'down'} {what:15} {url}", "32" if up(url) else "33")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")
    for env in ("sut", "virtual"):
        p = sub.add_parser(env)
        p.add_argument("action", choices=["start", "stop", "status"])
    p = sub.add_parser("test")
    p.add_argument("suite", choices=list(SUITES))
    p.add_argument("--headed", action="store_true", help="show the browser (slowed down) for UI suites")
    p = sub.add_parser("all")
    p.add_argument("--headed", action="store_true")
    p.add_argument("--keep-running", action="store_true", help="leave the servers up afterwards")
    p.add_argument("--skip", nargs="*", default=[], choices=list(SUITES))
    sub.add_parser("report")
    a = ap.parse_args(argv)

    if a.cmd == "doctor":
        return doctor()
    if a.cmd in ("sut", "virtual"):
        names = ["creditlens-api", "ui-real"] if a.cmd == "sut" else ["wiremock", "ui-virtual"]
        if a.action == "start":
            sut_start() if a.cmd == "sut" else virtual_start()
        elif a.action == "stop":
            stop(names)
        else:
            doctor()
        return 0
    if a.cmd == "test":
        return run_suite(a.suite, a.headed)
    if a.cmd == "report":
        say(f"Report: {write_index()}")
        return 0

    # all: the full pipeline
    settings.REPORTS.mkdir(exist_ok=True)
    for f in settings.REPORTS.glob("junit-*.xml"):
        f.unlink()
    (settings.REPORTS / "trace-results.json").unlink(missing_ok=True)
    started = []
    codes = {}
    try:
        started += sut_start()
        started += virtual_start()
        for name in PIPELINE:
            if name in a.skip:
                continue
            codes[name] = run_suite(name, a.headed)
            if name == "smoke" and codes[name] != 0:
                say("Smoke tests failed: stopping the pipeline here (fix the environment first).", "31")
                break
    finally:
        if not a.keep_running:
            say("\nStopping servers this run started")
            stop(reversed(started))
    index = write_index(codes)
    failed = [n for n, c in codes.items() if c != 0]
    say(f"\nReport: {index}", "1;32" if not failed else "1;31")
    say("All suites passed." if not failed else f"Failed suites: {', '.join(failed)}", "1;32" if not failed else "1;31")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
