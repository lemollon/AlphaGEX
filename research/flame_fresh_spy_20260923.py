"""Isolated research entrypoint; no live strategy or broker-order imports."""
import runpy
if __name__ == "__main__":
    runpy.run_module("flame_dual_extension_v1", run_name="__main__")
