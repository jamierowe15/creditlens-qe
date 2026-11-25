"""Security checks a QE can automate on every build (OWASP API Security Top 10 basics).
The deeper scan (OWASP ZAP baseline) runs in the CI pipeline, see .github/workflows/qe.yml."""
import pytest

from testdata.builders import an_applicant

pytestmark = [pytest.mark.api, pytest.mark.security]

SECURE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


@pytest.mark.req("CL-NFR01")
@pytest.mark.parametrize("method,path,body", [
    ("GET", "/api/stats", None),
    ("GET", "/api/applications", None),
    ("POST", "/api/applications", {}),           # error responses need the headers too
    ("GET", "/api/applications/987654321", None),
])
def test_secure_headers_on_api_responses(api, method, path, body):
    r = api.request(method, path, json=body)
    for header, value in SECURE_HEADERS.items():
        assert r.headers.get(header) == value, f"{method} {path}: {header}={r.headers.get(header)}"


@pytest.mark.req("CL-NFR01")
@pytest.mark.parametrize("raw", ['{"creditScore": 1e999}', '[]', '{"annualIncome": {"$gt": 0}}', "\x00\x01"])
def test_errors_never_leak_internals(api, raw):
    r = api.request("POST", "/api/applications", data=raw.encode(), headers={"Content-Type": "application/json"})
    assert r.status_code < 500 or "Quote reference" in r.text
    leaked = [w for w in ("Exception", "at com.", "springframework", "hibernate", "SQL", "jakarta.") if w in r.text]
    assert not leaked, f"response leaks {leaked}: {r.text[:300]}"


@pytest.mark.req("CL-NFR01")
@pytest.mark.parametrize("bad_id", ["abc\r\nFAKE LOG LINE", "short", "x" * 65, "<script>"])
def test_unsafe_correlation_ids_are_replaced(api, bad_id):
    r = api.request("GET", "/api/stats", headers={"X-Correlation-Id": bad_id.replace("\r\n", "%0d%0a")})
    returned = r.headers["X-Correlation-Id"]
    assert returned != bad_id and "FAKE" not in returned and "<" not in returned


@pytest.mark.req("CL-NFR01")
def test_cors_allows_only_the_known_front_end(api):
    ok = api.request("OPTIONS", "/api/stats", headers={"Origin": "http://localhost:4200", "Access-Control-Request-Method": "GET"})
    evil = api.request("OPTIONS", "/api/stats", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("Access-Control-Allow-Origin") == "http://localhost:4200"
    assert "Access-Control-Allow-Origin" not in evil.headers
    assert evil.status_code == 403


@pytest.mark.req("CL-NFR01")
@pytest.mark.parametrize("payload", ["Robert'); DROP TABLE credit_application;--", "' OR '1'='1", "<img src=x onerror=alert(1)>"])
def test_injection_strings_are_stored_as_plain_data(api, payload):
    r = api.submit(an_applicant().with_(applicantName=payload).build())
    assert r.status_code == 201
    assert api.get_application(r.json()["id"]).json()["applicantName"] == payload
    assert api.stats().status_code == 200, "database still answers after the payload"


@pytest.mark.req("CL-NFR01")
def test_methods_outside_the_api_contract_are_refused(api):
    for method in ("PUT", "DELETE", "PATCH"):
        assert api.request(method, "/api/applications/1").status_code in (403, 405), method
