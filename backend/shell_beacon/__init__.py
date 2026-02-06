"""
Tsushin Shell Beacon - Remote Command Execution Agent

A lightweight Python beacon client that polls the Tsushin backend for
commands and executes them locally. Part of the Shell Skill C2 architecture.

Phase 18: Shell Skill - Phase 2 Implementation
"""

__version__ = "1.0.0"
__author__ = "Tsushin"

from .beacon import Beacon
from .config import BeaconConfig
from .executor import CommandExecutor

__all__ = ["Beacon", "BeaconConfig", "CommandExecutor", "__version__"]
