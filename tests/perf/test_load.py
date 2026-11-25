"""Performance test as a pass/fail gate: run Locust headless, then compare p95 latency and the
error rate with the SLOs in perf/thresholds.json. The full HTML report lands in reports/perf/."""
import csv
import json
import os
import subprocess
import sys

import pytest

from config import settings

pytestmark = pytest.mark.perf

T = json.loads((settings.ROOT / "perf" / "thresholds.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def load_run(api):
    out = settings.REPORTS / "perf"
    out.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "locust", "-f", str(settings.ROOT / "perf" / "locustfile.py"), "--headless",
           "--host", settings.API_URL, "-u", str(T["users"]), "-r", str(T["spawn_rate"]),
           "--run-time", os.environ.get("QE_PERF_RUNTIME", T["run_time"]), "--only-summary",
           "--csv", str(out / "locust"), "--html", str(out / "load-report.html")]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    (out / "locust-console.txt").write_text(proc.stdout + proc.stderr, encoding="utf-8")
    with open(out / "locust_stats.csv", newline="", encoding="utf-8") as f:
        return {row["Name"]: row for row in csv.DictReader(f)}


@pytest.mark.req("CL-NFR02")
def test_no_errors_under_load(load_run):
    total = load_run["Aggregated"]
    requests_, failures = int(total["Request Count"]), int(total["Failure Count"])
    assert requests_ > 50, f"load test barely ran ({requests_} requests)"
    assert failures / requests_ <= T["max_failure_ratio"], f"{failures} of {requests_} requests failed"


@pytest.mark.req("CL-NFR02")
@pytest.mark.parametrize("endpoint,limit", list(T["p95_ms"].items()))
def test_p95_latency_within_slo(load_run, endpoint, limit):
    row = load_run.get(endpoint)
    assert row, f"no traffic recorded for {endpoint}"
    p95 = float(row["95%"])
    assert p95 <= limit, f"{endpoint}: p95 {p95:.0f} ms > SLO {limit} ms"
