"""
Smart process management for Tsushin backend and frontend servers.

This script safely starts/stops/restarts the backend (FastAPI) and frontend (Next.js)
servers by tracking process IDs in files, rather than blindly killing all Python/Node processes.

Linux-compatible version.
"""

import os
import sys
import time
import signal
import subprocess
import psutil
from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
PID_DIR = PROJECT_ROOT / "ops" / ".pids"

# PID files (using service names)
BACKEND_PID_FILE = PID_DIR / "tsn-core.pid"
FRONTEND_PID_FILE = PID_DIR / "tsushin-frontend.pid"


def ensure_pid_dir():
    """Create PID directory if it doesn't exist."""
    PID_DIR.mkdir(parents=True, exist_ok=True)


def read_pid(pid_file: Path) -> int:
    """Read PID from file."""
    if not pid_file.exists():
        return None

    try:
        with open(pid_file, 'r') as f:
            return int(f.read().strip())
    except (ValueError, IOError):
        return None


def write_pid(pid_file: Path, pid: int):
    """Write PID to file."""
    ensure_pid_dir()
    with open(pid_file, 'w') as f:
        f.write(str(pid))


def is_process_running(pid: int) -> bool:
    """Check if process with given PID is running."""
    if pid is None:
        return False

    try:
        process = psutil.Process(pid)
        return process.is_running()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def kill_process_tree(pid: int, name: str = "Process", timeout: int = 5):
    """Kill a process and all its children using Linux signals."""
    if not is_process_running(pid):
        print(f"[X] {name} (PID {pid}) is not running")
        return False

    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)

        # Send SIGTERM first (graceful shutdown)
        print(f"[STOP] Sending SIGTERM to {name} (PID {pid}) and {len(children)} children...")
        for child in children:
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                pass

        try:
            parent.terminate()
        except psutil.NoSuchProcess:
            pass

        # Wait for processes to exit gracefully
        gone, alive = psutil.wait_procs([parent] + children, timeout=timeout)

        # Force kill remaining processes with SIGKILL
        if alive:
            print(f"[KILL] Force killing {len(alive)} remaining processes...")
            for p in alive:
                try:
                    p.kill()
                except psutil.NoSuchProcess:
                    pass

            # Wait again
            psutil.wait_procs(alive, timeout=2)

        print(f"[OK] {name} (PID {pid}) stopped successfully")
        return True

    except psutil.NoSuchProcess:
        print(f"[X] {name} (PID {pid}) already terminated")
        return True
    except Exception as e:
        print(f"[ERROR] Error killing {name}: {e}")
        return False


def get_process_on_port(port: int):
    """Find process using specified port on Linux."""
    try:
        # Use ss command (modern replacement for netstat)
        result = subprocess.run(
            ['ss', '-tlnp', f'sport = :{port}'],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.stdout:
            lines = result.stdout.strip().split('\n')
            for line in lines[1:]:  # Skip header
                if 'LISTEN' in line:
                    # Extract PID from format: users:(("process",pid=12345,fd=3))
                    import re
                    match = re.search(r'pid=(\d+)', line)
                    if match:
                        pid = int(match.group(1))
                        try:
                            proc = psutil.Process(pid)
                            return {
                                'pid': pid,
                                'name': proc.name(),
                                'cmdline': ' '.join(proc.cmdline()[:3])
                            }
                        except psutil.NoSuchProcess:
                            pass

        return None

    except subprocess.TimeoutExpired:
        print(f"[WARN] Timeout checking port {port}")
        return None
    except Exception as e:
        print(f"[WARN] Error checking port {port}: {e}")
        return None


def kill_port_process(port: int, service_name: str = "Service"):
    """Kill any process using the specified port."""
    try:
        proc_info = get_process_on_port(port)

        if proc_info:
            print(f"[KILL] Port {port} occupied by {proc_info['name']} (PID {proc_info['pid']})")
            print(f"       Command: {proc_info['cmdline']}")

            kill_process_tree(proc_info['pid'], f"{service_name} on port {port}")

            # Verify port is free
            time.sleep(1)
            if get_process_on_port(port):
                print(f"[ERROR] Port {port} still occupied after cleanup!")
                return False

            print(f"[OK] Port {port} is now free")
            return True
        else:
            print(f"[OK] Port {port} is already free")
            return True

    except Exception as e:
        print(f"[ERROR] Port cleanup failed: {e}")
        return False


def stop_backend():
    """Stop backend server with zombie process detection."""
    print("\n[STOP] Stopping tsn-core...")
    pid = read_pid(BACKEND_PID_FILE)

    # First, try to stop the PID from file
    if pid and kill_process_tree(pid, "Backend"):
        BACKEND_PID_FILE.unlink(missing_ok=True)
        # Also check for zombie processes on port 8081
        print("[CLEANUP] Checking for zombie processes on port 8081...")
        kill_port_process(8081, "Backend")
        return True

    print("[INFO] Backend PID file not found or process not running")
    BACKEND_PID_FILE.unlink(missing_ok=True)
    # Still check for stale/zombie processes on port
    print("[CLEANUP] Checking for zombie processes on port 8081...")
    kill_port_process(8081, "Backend")
    return False


def stop_frontend():
    """Stop frontend server."""
    print("\n[STOP] Stopping tsushin-frontend...")
    pid = read_pid(FRONTEND_PID_FILE)

    if pid and kill_process_tree(pid, "Frontend"):
        FRONTEND_PID_FILE.unlink(missing_ok=True)
        # Also check for any other processes on port 3030
        kill_port_process(3030, "Frontend")
        return True

    print("[INFO] Frontend was not running")
    FRONTEND_PID_FILE.unlink(missing_ok=True)
    # Still check for stale processes on port
    kill_port_process(3030, "Frontend")
    return False


def clear_python_cache(directory):
    """Clear Python bytecode cache in directory."""
    import shutil
    cache_count = 0
    for cache_dir in Path(directory).rglob("__pycache__"):
        try:
            shutil.rmtree(cache_dir)
            cache_count += 1
        except Exception:
            pass
    if cache_count > 0:
        print(f"[CACHE] Cleared {cache_count} __pycache__ directories")


def start_backend():
    """Start backend server with zombie detection."""
    print("\n[START] Starting tsn-core (backend)...")

    # Check if already running via PID file
    pid = read_pid(BACKEND_PID_FILE)
    if pid and is_process_running(pid):
        # Verify PID matches port 8081
        proc_info = get_process_on_port(8081)
        if proc_info and proc_info['pid'] == pid:
            print(f"[OK] Backend already running (PID {pid})")
            return pid
        else:
            print(f"[ERROR] PID MISMATCH DETECTED!")
            print(f"        PID file says: {pid}")
            if proc_info:
                print(f"        Port 8081 occupied by: PID {proc_info['pid']}")
            print(f"[FIX] Killing zombie process and restarting...")
            kill_process_tree(pid, "Stale backend")
            BACKEND_PID_FILE.unlink(missing_ok=True)
            # Kill whatever is on port 8081
            kill_port_process(8081, "Backend")
            time.sleep(2)

    # Check for zombie processes on port 8081
    print("[CLEANUP] Ensuring port 8081 is free...")
    kill_port_process(8081, "Backend")
    time.sleep(1)

    # Clear Python cache to ensure fresh imports
    clear_python_cache(BACKEND_DIR)

    # Start backend
    os.chdir(BACKEND_DIR)

    # Open log file for output (prevents stdout/stderr pipe blocking)
    log_file_path = BACKEND_DIR / "logs" / "backend.log"
    log_file_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Backend logs: {log_file_path}")

    # Open log file (will remain open for process lifetime)
    log_file = open(log_file_path, 'w')

    # Activate virtual environment and start uvicorn
    venv_python = BACKEND_DIR / "venv" / "bin" / "python3"

    if not venv_python.exists():
        print(f"[ERROR] Virtual environment not found at {venv_python}")
        print(f"        Run: cd backend && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt")
        return None

    # Note: --reload removed due to persona router registration issue
    process = subprocess.Popen(
        [str(venv_python), "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8081"],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True  # Linux equivalent of CREATE_NEW_PROCESS_GROUP
    )

    write_pid(BACKEND_PID_FILE, process.pid)
    print(f"[OK] Backend started (PID {process.pid})")
    print(f"     URL: http://127.0.0.1:8081")

    # Wait a bit to check if it crashes immediately
    time.sleep(3)
    if not is_process_running(process.pid):
        print("[ERROR] Backend crashed immediately after start")
        print(f"        Check logs: {log_file_path}")
        BACKEND_PID_FILE.unlink(missing_ok=True)
        return None

    return process.pid


def start_frontend():
    """Start frontend server with resilient startup."""
    print("\n[START] Starting tsushin-frontend...")

    # Check if already running via PID file
    pid = read_pid(FRONTEND_PID_FILE)
    if pid and is_process_running(pid):
        print(f"[WARN] Frontend already running (PID {pid})")
        # Verify it's actually on port 3030
        proc_info = get_process_on_port(3030)
        if proc_info and proc_info['pid'] == pid:
            print(f"[OK] Verified frontend on port 3030")
            return pid
        else:
            print(f"[WARN] PID {pid} exists but not on port 3030, cleaning up...")
            kill_process_tree(pid, "Stale frontend")
            FRONTEND_PID_FILE.unlink(missing_ok=True)

    # AGGRESSIVE port cleanup - kill everything on 3030
    print("[CLEANUP] Ensuring port 3030 is free...")
    if not kill_port_process(3030, "Frontend"):
        print("[ERROR] Could not free port 3030")
        return None

    # Extra wait for port release
    print("[WAIT] Waiting for port 3030 to be released...")
    time.sleep(2)

    # Verify port is actually free
    if get_process_on_port(3030):
        print(f"[ERROR] Port 3030 still occupied")
        return None

    print("[OK] Port 3030 is free")

    # Start frontend
    os.chdir(FRONTEND_DIR)

    # Open log file for output (prevents stdout/stderr pipe blocking)
    log_file_path = FRONTEND_DIR / "logs" / "frontend.log"
    log_file_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[START] Launching npm run dev (output: {log_file_path})...")

    # Open log file (will remain open for process lifetime)
    log_file = open(log_file_path, 'w')

    # Check if .next build exists
    next_dir = FRONTEND_DIR / ".next"
    if next_dir.exists():
        # Production mode
        print(f"[INFO] Using production build (npm start)")
        npm_command = ["npm", "run", "start"]
    else:
        # Development mode
        print(f"[INFO] No production build found, using development mode (npm run dev)")
        npm_command = ["npm", "run", "dev"]

    process = subprocess.Popen(
        npm_command,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True  # Linux equivalent of CREATE_NEW_PROCESS_GROUP
    )

    write_pid(FRONTEND_PID_FILE, process.pid)
    print(f"[OK] Frontend process started (PID {process.pid})")
    print(f"     URL: http://localhost:3030")

    # Wait for Next.js to start
    print("[WAIT] Waiting for Next.js to initialize...")
    time.sleep(5)

    # Check if process is still alive
    if not is_process_running(process.pid):
        print("[ERROR] Frontend crashed immediately after start")
        print(f"        Check logs: {log_file_path}")
        FRONTEND_PID_FILE.unlink(missing_ok=True)
        return None

    # Verify port 3030 is now occupied by our process
    proc_info = get_process_on_port(3030)
    if proc_info:
        print("[OK] Frontend successfully bound to port 3030")
        return process.pid
    else:
        print("[WARN] Frontend started but not yet on port 3030, may still be starting...")
        return process.pid


def status():
    """Show status of backend and frontend."""
    print("\n[STATUS] Server Status")
    print("=" * 50)

    # Backend status
    backend_pid = read_pid(BACKEND_PID_FILE)
    if backend_pid and is_process_running(backend_pid):
        print(f"[OK] tsn-core: Running (PID {backend_pid})")
        print(f"     URL: http://127.0.0.1:8081")

        # Check if actually on port
        proc_info = get_process_on_port(8081)
        if proc_info and proc_info['pid'] != backend_pid:
            print(f"[WARN] Port 8081 occupied by different PID: {proc_info['pid']}")
    else:
        print("[X] tsn-core: Not running")
        BACKEND_PID_FILE.unlink(missing_ok=True)

    # Frontend status
    frontend_pid = read_pid(FRONTEND_PID_FILE)
    if frontend_pid and is_process_running(frontend_pid):
        print(f"[OK] tsushin-frontend: Running (PID {frontend_pid})")
        print(f"     URL: http://localhost:3030")

        # Check if actually on port
        proc_info = get_process_on_port(3030)
        if proc_info and proc_info['pid'] != frontend_pid:
            print(f"[WARN] Port 3030 occupied by different PID: {proc_info['pid']}")
    else:
        print("[X] tsushin-frontend: Not running")
        FRONTEND_PID_FILE.unlink(missing_ok=True)


def restart_backend():
    """Restart backend server."""
    stop_backend()
    time.sleep(2)
    return start_backend()


def restart_frontend():
    """Restart frontend server."""
    stop_frontend()
    time.sleep(2)
    return start_frontend()


def restart_all():
    """Restart both servers."""
    stop_backend()
    stop_frontend()
    time.sleep(2)
    start_backend()
    time.sleep(3)
    start_frontend()


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Manage Tsushin servers (Linux)")
    parser.add_argument(
        "action",
        choices=["start", "stop", "restart", "status"],
        help="Action to perform"
    )
    parser.add_argument(
        "target",
        nargs="?",
        choices=["backend", "frontend", "all"],
        default="all",
        help="Target server (default: all)"
    )

    args = parser.parse_args()

    if args.action == "status":
        status()

    elif args.action == "start":
        if args.target in ["backend", "all"]:
            start_backend()
        if args.target in ["frontend", "all"]:
            time.sleep(3) if args.target == "all" else None
            start_frontend()
        time.sleep(2)
        status()

    elif args.action == "stop":
        if args.target in ["backend", "all"]:
            stop_backend()
        if args.target in ["frontend", "all"]:
            stop_frontend()
        time.sleep(1)
        status()

    elif args.action == "restart":
        if args.target == "backend":
            restart_backend()
        elif args.target == "frontend":
            restart_frontend()
        else:  # all
            restart_all()
        time.sleep(2)
        status()


if __name__ == "__main__":
    main()
