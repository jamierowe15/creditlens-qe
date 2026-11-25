"""Tiny client for WireMock's admin API (service virtualization).

Base stubs live in virtualization/mappings (the "happy" virtual CreditLens).
A test can push a temporary override with a higher priority (lower number), e.g. "make /api/stats
return 500" or "answer the list after 3 seconds", and reset() puts the base stubs back."""
from __future__ import annotations

import requests

from config import settings

JSON = {"Content-Type": "application/json"}
PROBLEM = {"Content-Type": "application/problem+json"}


class WireMock:
    def __init__(self, base_url: str = settings.VIRTUAL_API_URL):
        self.admin = f"{base_url}/__admin"

    def is_up(self) -> bool:
        try:
            return requests.get(f"{self.admin}/mappings", timeout=3).ok
        except requests.RequestException:
            return False

    def reset(self) -> None:
        requests.post(f"{self.admin}/mappings/reset", timeout=5).raise_for_status()
        requests.delete(f"{self.admin}/requests", timeout=5).raise_for_status()

    def stub(self, method: str, url_path: str, status: int = 200, body=None, *, headers=None,
             delay_ms: int = 0, fault: str | None = None, priority: int = 1) -> dict:
        response: dict = {"status": status, "headers": headers or (PROBLEM if status >= 400 else JSON)}
        if body is not None:
            response["jsonBody"] = body
        if delay_ms:
            response["fixedDelayMilliseconds"] = delay_ms
        if fault:
            response = {"fault": fault}  # e.g. CONNECTION_RESET_BY_PEER, MALFORMED_RESPONSE_CHUNK
        mapping = {"priority": priority, "request": {"method": method, "urlPath": url_path}, "response": response}
        r = requests.post(f"{self.admin}/mappings", json=mapping, timeout=5)
        r.raise_for_status()
        return r.json()

    def requests_to(self, method: str, url_path: str) -> list[dict]:
        r = requests.post(f"{self.admin}/requests/find", json={"method": method, "urlPath": url_path}, timeout=5)
        r.raise_for_status()
        return r.json()["requests"]

    def mapping_bodies(self) -> list[tuple[str, dict]]:
        """(mapping name, response JSON) for every base stub, used to check stubs against the contract."""
        import json
        from config.settings import ROOT
        out = []
        for m in sorted((ROOT / "virtualization" / "mappings").glob("*.json")):
            spec = json.loads(m.read_text(encoding="utf-8"))
            resp = spec["response"]
            if "bodyFileName" in resp and "{{" not in resp["bodyFileName"]:
                out.append((spec["name"], json.loads((ROOT / "virtualization" / "__files" / resp["bodyFileName"]).read_text(encoding="utf-8"))))
            elif "jsonBody" in resp:
                out.append((spec["name"], resp["jsonBody"]))
        return out
