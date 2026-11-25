"""Serve the built Angular app and forward /api and /actuator calls to a backend.

Why: the same compiled front end can be pointed at the REAL API (port 8080) or at WireMock
(port 8089) just by changing --api. That is how the virtualized UI tests work.

    python tools/spa_proxy.py --dist ../creditlens/frontend/dist/frontend/browser --port 4400 --api http://localhost:8080
"""
from __future__ import annotations

import argparse
import http.client
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

FORWARD = ("/api/", "/actuator", "/__admin")
HOP_BY_HOP = {"connection", "keep-alive", "transfer-encoding", "te", "trailer", "upgrade", "proxy-authorization", "proxy-authenticate"}


def make_handler(dist: Path, api: str):
    target = urlsplit(api)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # keep the console quiet; failures still show in tests
            pass

        def _forward(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else None
            # The browser sees this proxy as the site itself, so to the API every call is same-origin.
            # Drop Origin, like a real gateway does: otherwise CreditLens' strict CORS rule (only
            # http://localhost:4200) rejects every POST from port 4400 with 403 "Invalid CORS request".
            headers = {k: v for k, v in self.headers.items()
                       if k.lower() not in HOP_BY_HOP and k.lower() not in ("host", "origin")}
            conn = http.client.HTTPConnection(target.hostname, target.port or 80, timeout=60)
            try:
                conn.request(self.command, self.path, body=body, headers=headers)
                resp = conn.getresponse()
                data = resp.read()
            except OSError:
                # Backend down: answer like a real gateway would, so the UI shows its "cannot reach" state.
                self.send_response(502)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            finally:
                conn.close()
            self.send_response(resp.status)
            for k, v in resp.getheaders():
                if k.lower() not in HOP_BY_HOP and k.lower() != "content-length":
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _static(self):
            path = urlsplit(self.path).path
            file = (dist / path.lstrip("/")).resolve()
            if not str(file).startswith(str(dist)) or not file.is_file():
                file = dist / "index.html"  # single-page app: unknown paths are Angular routes
            data = file.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(file.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def _route(self):
            if self.path.startswith(FORWARD):
                self._forward()
            else:
                self._static()

        do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_HEAD = _route

    return Handler


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dist", required=True)
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--api", required=True)
    a = ap.parse_args(argv)
    dist = Path(a.dist).resolve()
    if not (dist / "index.html").exists():
        sys.exit(f"No index.html in {dist}. Build the front end first (npm run build).")
    print(f"Serving {dist} on http://localhost:{a.port}  ->  API {a.api}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(dist, a.api)).serve_forever()


if __name__ == "__main__":
    main()
