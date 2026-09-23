"""Research-service entrypoint. The previous source audit is retained in Git history.

The controlled runner stays disabled unless FLAME_FRESH_MODE is explicitly set
to controlled-rerun. No broker orders or production database access.
"""
import runpy

if __name__ == '__main__':
    runpy.run_module('flame_controlled_rerun', run_name='__main__')
