"""Isolated research-service entrypoint; live trading is not imported."""
import runpy

if __name__ == '__main__':
    runpy.run_module('flame_reset_stock', run_name='__main__')
