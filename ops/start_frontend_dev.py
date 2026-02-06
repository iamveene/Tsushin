"""
Start frontend in development mode with proper output handling.

This script starts the Next.js dev server without redirecting stdout/stderr,
which can cause the server to hang on Windows.
"""

import os
import sys
import subprocess
from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
PID_DIR = PROJECT_ROOT / "ops" / ".pids"
FRONTEND_PID_FILE = PID_DIR / "frontend.pid"

def ensure_pid_dir():
    """Create PID directory if it doesn't exist."""
    PID_DIR.mkdir(parents=True, exist_ok=True)

def write_pid(pid_file: Path, pid: int):
    """Write PID to file."""
    ensure_pid_dir()
    with open(pid_file, 'w') as f:
        f.write(str(pid))

def start_frontend():
    """Start frontend server."""
    print("[START] Starting frontend in development mode...")
    print(f"[INFO] Working directory: {FRONTEND_DIR}")

    os.chdir(FRONTEND_DIR)

    # Start npm run dev in a new console window (Windows)
    if sys.platform == 'win32':
        # Use start command to open in new window
        process = subprocess.Popen(
            'start "Tsushin Frontend" cmd /k "npm run dev"',
            shell=True
        )
        # Give it a moment to start
        import time
        time.sleep(2)

        # Find the actual node process
        result = subprocess.run(
            'wmic process where "CommandLine like \'%next%start-server%\'" get ProcessId',
            shell=True,
            capture_output=True,
            text=True
        )

        lines = result.stdout.strip().split('\n')
        if len(lines) > 1:
            try:
                pid = int(lines[1].strip())
                write_pid(FRONTEND_PID_FILE, pid)
                print(f"[OK] Frontend started in new window (PID {pid})")
                print(f"[OK] URL: http://localhost:3030")
                print(f"[INFO] Frontend will run in separate console window")
                print(f"[INFO] Close the window or use Ctrl+C in that window to stop")
                return pid
            except (ValueError, IndexError):
                print("[WARN] Could not track frontend PID, but server should be starting...")
                print("[OK] URL: http://localhost:3030")
                return None
    else:
        # Unix: run in background
        process = subprocess.Popen(
            ["npm", "run", "dev"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL
        )
        write_pid(FRONTEND_PID_FILE, process.pid)
        print(f"[OK] Frontend started (PID {process.pid})")
        print(f"[OK] URL: http://localhost:3030")
        return process.pid

if __name__ == '__main__':
    start_frontend()
