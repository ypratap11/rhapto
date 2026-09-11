"""Serve the discovery fixtures over HTTP so smoke runs never touch a vendor. Usage: python scripts/discovery-fixture-server.py 8089"""

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "apps" / "api" / "tests" / "fixtures" / "discovery"
ROUTES: dict[str, object] = {}
for path in FIXTURES.glob("*.json"):
    ROUTES.update(json.loads(path.read_text(encoding="utf-8")))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        for key, body in ROUTES.items():
            if key.split("/", 1)[-1] in self.path or key in self.path:
                payload = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
        self.send_response(404)
        self.end_headers()

    def log_message(self, *args: object) -> None:
        return


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", int(sys.argv[1]) if len(sys.argv) > 1 else 8089), Handler).serve_forever()
