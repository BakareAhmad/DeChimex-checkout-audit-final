#!/usr/bin/env python3
"""Minimal Brevo stub: captures sent email payloads to /tmp/brevo_nav_audit.jsonl."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

OUT = "/tmp/brevo_nav_audit.jsonl"

class H(BaseHTTPRequestHandler):
    def _read(self):
        te = (self.headers.get("Transfer-Encoding") or "").lower()
        if "chunked" in te:
            chunks = []
            while True:
                size_line = self.rfile.readline().strip()
                try:
                    size = int(size_line.split(b";")[0], 16)
                except ValueError:
                    break
                if size == 0:
                    self.rfile.readline()
                    break
                chunks.append(self.rfile.read(size))
                self.rfile.readline()
            return b"".join(chunks)
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def do_POST(self):
        body = self._read()
        try:
            data = json.loads(body.decode("utf-8", "replace"))
        except Exception:
            data = {"raw": body.decode("utf-8", "replace")}
        with open(OUT, "a") as f:
            f.write(json.dumps({"path": self.path, "body": data}) + "\n")
        self.send_response(201 if "smtp" in self.path else 200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"messageId":"stub"}')

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def log_message(self, *a):
        pass

print("brevo stub listening on 0.0.0.0:8899, capture ->", OUT)
HTTPServer(("0.0.0.0", 8899), H).serve_forever()
