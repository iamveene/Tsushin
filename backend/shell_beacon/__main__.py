#!/usr/bin/env python3
"""
Entry point for running shell_beacon as a module.

Usage:
    python -m shell_beacon [options]
"""

from .beacon import main

if __name__ == "__main__":
    exit(main())
