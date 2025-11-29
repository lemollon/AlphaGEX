"""
Console Output Utilities

Replaces Streamlit UI functions with console output.
All UI-related functions now output to console/logs instead.
"""

import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-7s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)


class ConsoleUI:
    """
    Console-based replacement for Streamlit UI functions.

    Usage:
        from utils.console_output import ui
        ui.info("Processing...")
        ui.error("Failed!")
        ui.metric("Price", 450.00, "+2.5%")
    """

    class session_state:
        """Mock session state using a dictionary"""
        _state = {}

        @classmethod
        def get(cls, key, default=None):
            return cls._state.get(key, default)

        @classmethod
        def __setattr__(cls, key, value):
            if key != '_state':
                cls._state[key] = value
            else:
                super().__setattr__(key, value)

        @classmethod
        def __getattr__(cls, key):
            return cls._state.get(key)

    class secrets:
        """Mock secrets - reads from environment variables"""
        import os

        @classmethod
        def get(cls, key, default=""):
            import os
            return os.environ.get(key, default)

    @staticmethod
    def error(msg):
        """Display error message"""
        logger.error(msg)

    @staticmethod
    def warning(msg):
        """Display warning message"""
        logger.warning(msg)

    @staticmethod
    def info(msg):
        """Display info message"""
        logger.info(msg)

    @staticmethod
    def write(msg):
        """Write text output"""
        print(msg)

    @staticmethod
    def success(msg):
        """Display success message"""
        logger.info(f"✓ {msg}")

    @staticmethod
    def metric(label, value, delta=None, help=None):
        """Display metric"""
        if delta:
            print(f"{label}: {value} ({delta})")
        else:
            print(f"{label}: {value}")

    @staticmethod
    def columns(n):
        """Return list of column placeholders"""
        class Column:
            def __enter__(self): return self
            def __exit__(self, *args): pass
        return [Column() for _ in range(n)]

    @staticmethod
    def sidebar():
        """Return sidebar placeholder"""
        class Sidebar:
            @staticmethod
            def header(text): print(f"\n=== {text} ===")
            @staticmethod
            def write(text): print(text)
            @staticmethod
            def selectbox(label, options, index=0): return options[index] if options else None
            @staticmethod
            def slider(label, min_val, max_val, value): return value
            @staticmethod
            def button(label): return False
        return Sidebar()

    @staticmethod
    def header(text):
        """Display header"""
        print(f"\n{'='*60}")
        print(f" {text}")
        print(f"{'='*60}")

    @staticmethod
    def subheader(text):
        """Display subheader"""
        print(f"\n--- {text} ---")

    @staticmethod
    def markdown(text):
        """Display markdown (just print)"""
        print(text)

    @staticmethod
    def dataframe(df):
        """Display dataframe"""
        print(df.to_string() if hasattr(df, 'to_string') else str(df))

    @staticmethod
    def plotly_chart(fig, use_container_width=False):
        """Display plotly chart (just log)"""
        logger.info("Chart: (plotly chart - view in notebook or save to file)")

    @staticmethod
    def spinner(text):
        """Context manager for spinner"""
        class Spinner:
            def __init__(self, text):
                self.text = text
            def __enter__(self):
                print(f"⏳ {self.text}...")
                return self
            def __exit__(self, *args):
                pass
        return Spinner(text)

    @staticmethod
    def progress(value):
        """Display progress bar"""
        bars = int(value * 20)
        print(f"[{'█' * bars}{'░' * (20-bars)}] {value*100:.0f}%")

    @staticmethod
    def expander(label, expanded=False):
        """Context manager for expander"""
        class Expander:
            def __init__(self, label):
                self.label = label
            def __enter__(self):
                print(f"\n▼ {self.label}")
                return self
            def __exit__(self, *args):
                pass
        return Expander(label)

    @staticmethod
    def tabs(labels):
        """Return tab placeholders"""
        class Tab:
            def __init__(self, label):
                self.label = label
            def __enter__(self):
                print(f"\n[Tab: {self.label}]")
                return self
            def __exit__(self, *args):
                pass
        return [Tab(label) for label in labels]

    @staticmethod
    def selectbox(label, options, index=0):
        """Select box - return default"""
        return options[index] if options else None

    @staticmethod
    def button(label, key=None):
        """Button - always return False in console mode"""
        return False

    @staticmethod
    def text_input(label, value="", key=None):
        """Text input - return default value"""
        return value

    @staticmethod
    def number_input(label, value=0, min_value=None, max_value=None, step=1):
        """Number input - return default value"""
        return value

    @staticmethod
    def checkbox(label, value=False):
        """Checkbox - return default value"""
        return value

    @staticmethod
    def radio(label, options, index=0):
        """Radio - return default"""
        return options[index] if options else None

    @staticmethod
    def empty():
        """Return empty placeholder"""
        class Empty:
            @staticmethod
            def write(msg): print(msg)
            @staticmethod
            def info(msg): logger.info(msg)
            @staticmethod
            def error(msg): logger.error(msg)
        return Empty()

    @staticmethod
    def container():
        """Return container placeholder"""
        class Container:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            @staticmethod
            def write(msg): print(msg)
        return Container()

    @staticmethod
    def form(key):
        """Return form placeholder"""
        class Form:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            @staticmethod
            def form_submit_button(label): return False
        return Form()

    @staticmethod
    def toast(msg, icon=None):
        """Display toast notification"""
        logger.info(f"🔔 {msg}")

    @staticmethod
    def cache_data(func):
        """Decorator for caching - just return function as-is"""
        return func

    @staticmethod
    def cache_resource(func):
        """Decorator for caching - just return function as-is"""
        return func


# Global UI instance
ui = ConsoleUI()

# Alias for compatibility
st = ConsoleUI()
