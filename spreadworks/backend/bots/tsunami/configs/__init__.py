"""TSUNAMI configuration package.

Public API:
    GLOBAL                     platform-wide constants
    TSUNAMI_INSTANCES          dict[name -> InstanceConfig]
    InstanceConfig             per-LETF config dataclass
    get(name) / all_instances()
"""
from .global_config import GLOBAL, GlobalConfig
from .instances import TSUNAMI_INSTANCES, InstanceConfig, all_instances, get

__all__ = [
    "GLOBAL", "GlobalConfig",
    "TSUNAMI_INSTANCES", "InstanceConfig",
    "all_instances", "get",
]
