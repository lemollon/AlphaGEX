# Simple logger for GammaHunter
from datetime import datetime

def log_error(msg, exception=None):
    timestamp = datetime.now().strftime("%H:%M:%S")
    if exception:
        print(f"[ERROR {timestamp}] {msg} - {str(exception)}")
    else:
        print(f"[ERROR {timestamp}] {msg}")

def log_info(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[INFO {timestamp}] {msg}")

def log_warning(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[WARNING {timestamp}] {msg}")

def log_success(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[SUCCESS {timestamp}] {msg}")

def log_debug(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[DEBUG {timestamp}] {msg}")

class Logger:
    def info(self, msg):
        log_info(msg)
    def error(self, msg):
        log_error(msg)
    def warning(self, msg):
        log_warning(msg)
    def debug(self, msg):
        log_debug(msg)

logger = Logger()
