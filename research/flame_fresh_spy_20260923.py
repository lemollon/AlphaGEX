"""Isolated research entrypoint. Never imports customer execution or production DBs."""
import runpy

if __name__ == '__main__':
    runpy.run_module('flame_rerun_transport', run_name='__main__')
