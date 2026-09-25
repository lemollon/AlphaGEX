"""Isolated research status server.

Completed research is not auto-run on web-service restart. Historical runs are
triggered explicitly so Render restarts cannot replay completed work.
"""
import os
from http.server import HTTPServer, BaseHTTPRequestHandler

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body=b'{"status":"idle","research_autorun":false,"live_changed":false}'
        self.send_response(200)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, fmt, *args):
        return

if __name__ == "__main__":
    HTTPServer(("0.0.0.0", int(os.getenv("PORT","10000"))), Handler).serve_forever()
