"""Isolated Flame research worker in safe disabled state.
No research run starts automatically and no live/customer trading code is imported.
"""
import os
from http.server import HTTPServer
import flame_reset_baseline as core

core.STATE["stage"] = "disabled"

if __name__ == "__main__":
    HTTPServer(("0.0.0.0", int(os.getenv("PORT", "10000"))), core.Handler).serve_forever()
