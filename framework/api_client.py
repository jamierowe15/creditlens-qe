"""A thin API client. Tests talk to CreditLens through this class, never with raw URLs, so if an
endpoint moves only this file changes (same idea as the Angular CreditApiService)."""
from __future__ import annotations

import uuid
from typing import Any

import requests

from config import settings


class CreditLensApi:
    def __init__(self, base_url: str = settings.API_URL, timeout: float = settings.REQUEST_TIMEOUT):
        self.base_url = base_url
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["Accept"] = "application/json"

    # ---- low level -------------------------------------------------------------------------
    def request(self, method: str, path: str, *, correlation_id: str | None = None, **kwargs: Any) -> requests.Response:
        headers = kwargs.pop("headers", {}) or {}
        # Every test request carries its own correlation id, so a failure can be found in the API logs.
        headers.setdefault("X-Correlation-Id", correlation_id or f"qe-{uuid.uuid4()}")
        return self.session.request(method, f"{self.base_url}{path}", headers=headers, timeout=self.timeout, **kwargs)

    def get(self, path: str, **kw: Any) -> requests.Response:
        return self.request("GET", path, **kw)

    def post(self, path: str, body: Any = None, **kw: Any) -> requests.Response:
        return self.request("POST", path, json=body, **kw)

    # ---- domain level ----------------------------------------------------------------------
    def health(self, **kw: Any) -> requests.Response:
        return self.get("/actuator/health", **kw)

    def submit(self, body: dict) -> requests.Response:
        return self.post("/api/applications", body)

    def preview(self, body: dict) -> requests.Response:
        return self.post("/api/decisions/preview", body)

    def get_application(self, app_id: int | str) -> requests.Response:
        return self.get(f"/api/applications/{app_id}")

    def audit(self, app_id: int | str) -> requests.Response:
        return self.get(f"/api/applications/{app_id}/audit")

    def review(self, app_id: int | str, approve: bool, underwriter: str = "QE Underwriter",
               note: str = "Verified documents (automated test)") -> requests.Response:
        return self.post(f"/api/applications/{app_id}/review",
                         {"approve": approve, "underwriter": underwriter, "note": note})

    def list(self, **params: Any) -> requests.Response:
        return self.get("/api/applications", params=params)

    def stats(self, **kw: Any) -> requests.Response:
        return self.get("/api/stats", **kw)

    def is_up(self) -> bool:
        try:
            return self.health().json().get("status") == "UP"
        except Exception:
            return False
