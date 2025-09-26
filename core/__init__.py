"""
GammaHunter Core Module
======================
Core functionality for the GammaHunter trading system.
"""

__version__ = "1.0.0"
__author__ = "GammaHunter Team"

# Import key components for easy access
from .logger import logger, log_error, log_info, log_warning, log_success

__all__ = ['logger', 'log_error', 'log_info', 'log_warning', 'log_success']
