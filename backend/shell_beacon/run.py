#!/usr/bin/env python3
"""
Simple wrapper to run the Tsushin Shell Beacon.

This script can be executed directly from within the shell_beacon directory:
    python run.py --server URL --api-key KEY

Or make it executable and run:
    chmod +x run.py
    ./run.py --server URL --api-key KEY
"""

import sys
import os

# Add parent directory to path so we can import shell_beacon as a module
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
sys.path.insert(0, parent_dir)

# Now import and run
from shell_beacon.beacon import main

if __name__ == "__main__":
    sys.exit(main())
