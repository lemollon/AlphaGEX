"""Isolated Flame research dispatcher."""
import os
from http.server import HTTPServer, BaseHTTPRequestHandler

MODE = os.getenv("FLAME_FRESH_MODE", "").strip()

if MODE == "research-exit-repair-v1":
    from flame_research_exit_repair import execute, core
    import threading
    threading.Thread(target=execute, daemon=True).start()
    HTTPServer(("0.0.0.0", int(os.getenv("PORT", "10000"))), core.Handler).serve_forever()
elif MODE == "frozen28-exit-repair":
    from flame_frozen28_exit_repair import execute, core
    import threading
    threading.Thread(target=execute, daemon=True).start()
    HTTPServer(("0.0.0.0", int(os.getenv("PORT", "10000"))), core.Handler).serve_forever()
else:
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
        HTTPServer(("0.0.0.0", int(os.getenv("PORT", "10000"))), Handler).serve_forever()
