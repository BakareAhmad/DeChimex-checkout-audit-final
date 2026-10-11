"""Minimal Brevo (v3) stand-in for E2E runs.

Accepts any POST, appends the parsed JSON body to CAPTURE (one JSON object per line) and
answers 201 so DeChimex's BrevoEmailService treats the send as successful. That is how the
E2E reads the 6-digit email-verification code without a real inbox.

  python3 e2e/gradual-signup/brevo_stub.py [port]
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8899
CAPTURE = os.environ.get("BREVO_CAPTURE", "/home/user/e2e-gradual-wip/brevo_captured.jsonl")
os.makedirs(os.path.dirname(CAPTURE), exist_ok=True)


class Handler(BaseHTTPRequestHandler):
    def _respond(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._respond(200, {"status": "brevo-stub"})

    def _read_body(self):
        """DeChimex's HttpClient posts chunked (no Content-Length), so handle both."""
        length = self.headers.get("Content-Length")
        if length:
            return self.rfile.read(int(length)).decode("utf-8", "replace")
        if "chunked" in (self.headers.get("Transfer-Encoding") or "").lower():
            out = bytearray()
            while True:
                line = self.rfile.readline().strip()
                if not line:
                    continue
                size = int(line.split(b";")[0], 16)
                if size == 0:
                    self.rfile.readline()  # trailing CRLF
                    break
                out += self.rfile.read(size)
                self.rfile.readline()      # CRLF after each chunk
            return out.decode("utf-8", "replace")
        return ""

    def do_POST(self):
        raw = self._read_body()
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"raw": raw}
        with open(CAPTURE, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload) + "\n")
        self._respond(201, {"messageId": "stub-" + str(abs(hash(raw)) % 10**9)})

    def log_message(self, *args):  # keep the log quiet
        pass


if __name__ == "__main__":
    print(f"brevo stub listening on 0.0.0.0:{PORT}, capture -> {CAPTURE}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
