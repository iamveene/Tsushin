"""
Convenience script to restart backend using the smart process manager.
Replaces the old dangerous kill-all approach with safe PID-based management.

IMPORTANT: This script ensures:
1. Clean process termination (no orphaned processes)
2. Python cache is cleared before restart
3. New process is verified to be running
4. Port is actually bound and responding
"""

import subprocess
import sys
import time
import shutil
from pathlib import Path

def clear_python_cache():
    """Clear Python bytecode cache to ensure fresh imports."""
    backend_dir = Path(__file__).parent.parent / "backend"
    print("[CACHE] Clearing Python bytecode cache...")

    cache_count = 0
    for cache_dir in backend_dir.rglob("__pycache__"):
        try:
            shutil.rmtree(cache_dir)
            cache_count += 1
        except Exception as e:
            print(f"[WARN] Could not remove {cache_dir}: {e}")

    print(f"[OK] Cleared {cache_count} __pycache__ directories")

def verify_backend_running():
    """Verify backend is actually responding on port 8081."""
    import urllib.request
    import json

    max_attempts = 10
    for attempt in range(1, max_attempts + 1):
        try:
            print(f"[VERIFY] Attempt {attempt}/{max_attempts}: Checking http://127.0.0.1:8081/api/health")
            response = urllib.request.urlopen("http://127.0.0.1:8081/api/health", timeout=2)
            data = json.loads(response.read().decode())
            if data.get("status") == "ok":
                print("[OK] Backend is responding!")
                return True
        except Exception as e:
            if attempt < max_attempts:
                time.sleep(1)
            else:
                print(f"[ERROR] Backend not responding after {max_attempts} attempts: {e}")
                return False
    return False

if __name__ == "__main__":
    print("=" * 50)
    print("Backend Restart (Smart Process Manager)")
    print("=" * 50)

    # Clear cache before restart
    clear_python_cache()

    # Restart backend
    script_dir = Path(__file__).parent
    result = subprocess.run(
        [sys.executable, str(script_dir / "manage_servers.py"), "restart", "backend"],
        cwd=script_dir
    )

    if result.returncode != 0:
        print("[ERROR] Backend restart failed!")
        sys.exit(result.returncode)

    # Verify backend is actually running
    print("\n[VERIFY] Verifying backend is responding...")
    if verify_backend_running():
        print("\n" + "=" * 50)
        print("[SUCCESS] Backend restarted and verified!")
        print("=" * 50)
    else:
        print("\n" + "=" * 50)
        print("[WARNING] Backend process started but not responding!")
        print("Check logs: backend/logs/backend.log")
        print("=" * 50)
        sys.exit(1)
