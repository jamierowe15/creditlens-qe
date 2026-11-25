"""Load model for CreditLens: what a busy hour looks like.

Weights reflect real usage: people fiddle with the live preview far more often than they submit,
and underwriters refresh the dashboard. Run by tests/perf/test_load.py, or by hand with a web UI:
    locust -f perf/locustfile.py --host http://localhost:8080
"""
import random
import uuid

from locust import HttpUser, between, task

PROFILE = {
    "annualIncome": 85000, "monthlyDebtPayments": 400, "creditScore": 720, "requestedAmount": 12000,
    "termMonths": 48, "employmentStatus": "FULL_TIME", "productType": "PERSONAL_LOAN",
}


class Applicant(HttpUser):
    wait_time = between(0.2, 1.0)

    def _headers(self):
        return {"X-Correlation-Id": f"perf-{uuid.uuid4()}"}

    @task(6)
    def preview(self):
        body = {**PROFILE, "creditScore": random.randint(560, 820), "requestedAmount": random.choice([5000, 12000, 30000])}
        self.client.post("/api/decisions/preview", json=body, headers=self._headers(), name="POST /api/decisions/preview")

    @task(1)
    def submit(self):
        body = {**PROFILE, "applicantName": "Perf Test User", "email": f"perf.{uuid.uuid4().hex[:8]}@example.com",
                "creditScore": random.randint(560, 820)}
        with self.client.post("/api/applications", json=body, headers=self._headers(), name="POST /api/applications",
                              catch_response=True) as r:
            if r.status_code != 201:
                r.failure(f"expected 201, got {r.status_code}")


class Underwriter(HttpUser):
    wait_time = between(1, 3)
    weight = 1

    @task(3)
    def dashboard(self):
        self.client.get("/api/stats", name="GET /api/stats")
        self.client.get("/api/applications?page=0&size=10", name="GET /api/applications")

    @task(1)
    def referred_queue(self):
        self.client.get("/api/applications?status=REFERRED&size=20", name="GET /api/applications?status=REFERRED")
