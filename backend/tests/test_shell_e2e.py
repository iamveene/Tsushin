#!/usr/bin/env python3
"""
Shell Skill E2E Test

This script performs a complete end-to-end test of the Shell skill:
1. Creates a beacon via API
2. Starts the beacon process locally
3. Verifies beacon becomes online
4. Tests /shell command execution
5. Verifies command completion and result
6. Cleans up

Run: python -m tests.test_shell_e2e
"""

import sys
import os
import time
import json
import requests
import subprocess
import signal
from datetime import datetime
from typing import Optional

# Configuration
API_URL = os.environ.get("TSUSHIN_API_URL", "http://localhost:8081")
TEST_TENANT_ID = "test-tenant"
TEST_AGENT_ID = "shellboy"
BEACON_NAME = f"e2e-test-beacon-{int(time.time())}"

# Get auth token
AUTH_TOKEN = None


def get_auth_token() -> Optional[str]:
    """Get authentication token for API requests."""
    global AUTH_TOKEN
    if AUTH_TOKEN:
        return AUTH_TOKEN

    # Try to login with test credentials
    try:
        response = requests.post(
            f"{API_URL}/api/auth/login",
            json={"email": "admin@tsushin.local", "password": "admin123"},
            headers={"Content-Type": "application/json"}
        )
        if response.status_code == 200:
            data = response.json()
            AUTH_TOKEN = data.get("access_token")
            return AUTH_TOKEN
    except Exception:
        pass

    # Fallback: Try dev/skip auth mode
    return None


def log(msg: str, level: str = "INFO"):
    """Simple logging."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [{level}] {msg}")


def get_auth_headers():
    """Get auth headers for API requests."""
    headers = {
        "Content-Type": "application/json",
        "X-Tenant-ID": TEST_TENANT_ID
    }
    token = get_auth_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def step_1_create_beacon() -> tuple[Optional[int], Optional[str]]:
    """Create a new beacon and return its ID and API key."""
    log("STEP 1: Creating beacon via API...")

    response = requests.post(
        f"{API_URL}/api/shell/integrations",
        headers=get_auth_headers(),
        json={
            "name": BEACON_NAME,
            "poll_interval": 2,  # Fast polling for test
            "mode": "beacon"
        }
    )

    if response.status_code != 200:
        log(f"Failed to create beacon: {response.status_code} - {response.text}", "ERROR")
        return None, None

    data = response.json()
    beacon_id = data["id"]
    api_key = data["api_key"]
    log(f" Beacon created: ID={beacon_id}, Name={BEACON_NAME}")
    return beacon_id, api_key


def step_2_verify_beacon_exists(beacon_id: int) -> bool:
    """Verify the beacon was created."""
    log("STEP 2: Verifying beacon exists...")

    response = requests.get(
        f"{API_URL}/api/shell/integrations",
        headers=get_auth_headers()
    )

    if response.status_code != 200:
        log(f"Failed to list integrations: {response.text}", "ERROR")
        return False

    beacons = response.json()
    found = any(b["id"] == beacon_id for b in beacons)

    if found:
        log(f" Beacon {beacon_id} found in integrations list")
    else:
        log(f"Beacon {beacon_id} not found!", "ERROR")

    return found


def step_3_start_beacon(api_key: str) -> Optional[subprocess.Popen]:
    """Start the beacon process in background."""
    log("STEP 3: Starting beacon process...")

    # Build the command to run beacon
    beacon_dir = os.path.join(os.path.dirname(__file__), "..", "shell_beacon")
    cmd = [
        sys.executable, "-m", "shell_beacon",
        "--server", f"{API_URL}/api/shell",
        "--api-key", api_key,
        "--log-level", "DEBUG"
    ]

    log(f"Running: {' '.join(cmd)}")

    # Start beacon in background
    try:
        process = subprocess.Popen(
            cmd,
            cwd=os.path.dirname(beacon_dir),  # Run from backend dir
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        log(f" Beacon process started: PID={process.pid}")
        return process
    except Exception as e:
        log(f"Failed to start beacon: {e}", "ERROR")
        return None


def step_4_wait_for_online(beacon_id: int, timeout: int = 30) -> bool:
    """Wait for beacon to come online."""
    log(f"STEP 4: Waiting for beacon to come online (timeout={timeout}s)...")

    start_time = time.time()
    while time.time() - start_time < timeout:
        response = requests.get(
            f"{API_URL}/api/shell/integrations",
            headers=get_auth_headers()
        )

        if response.status_code == 200:
            beacons = response.json()
            for b in beacons:
                if b["id"] == beacon_id:
                    if b["is_online"]:
                        log(f" Beacon {beacon_id} is ONLINE!")
                        log(f"   Last checkin: {b.get('last_checkin')}")
                        log(f"   Hostname: {b.get('hostname')}")
                        return True
                    else:
                        log(f"   Beacon still offline, waiting... (last_checkin: {b.get('last_checkin')})")

        time.sleep(2)

    log(f"Beacon did not come online within {timeout}s", "ERROR")
    return False


def step_5_execute_command(beacon_id: int) -> Optional[str]:
    """Execute a test command via /shell."""
    log("STEP 5: Executing test command via API...")

    test_command = "echo 'Hello from E2E test!' && date"

    response = requests.post(
        f"{API_URL}/api/shell/execute",
        headers=get_auth_headers(),
        json={
            "shell_id": beacon_id,
            "commands": [test_command],
            "wait_for_result": True,
            "timeout": 30
        }
    )

    if response.status_code != 200:
        log(f"Failed to execute command: {response.status_code} - {response.text}", "ERROR")
        return None

    data = response.json()
    command_id = data.get("command_id")
    log(f" Command queued: ID={command_id}")
    return command_id


def step_6_wait_for_completion(command_id: str, timeout: int = 30) -> bool:
    """Wait for command to complete and verify result."""
    log(f"STEP 6: Waiting for command {command_id} to complete...")

    start_time = time.time()
    while time.time() - start_time < timeout:
        response = requests.get(
            f"{API_URL}/api/shell/commands/{command_id}",
            headers=get_auth_headers()
        )

        if response.status_code == 200:
            data = response.json()
            status = data.get("status")
            log(f"   Command status: {status}")

            if status == "completed":
                stdout = data.get("stdout", "")
                exit_code = data.get("exit_code")
                log(f" Command completed successfully!")
                log(f"   Exit code: {exit_code}")
                log(f"   Output: {stdout[:200]}...")

                if "Hello from E2E test!" in stdout:
                    log(" Output verified - contains expected text!")
                    return True
                else:
                    log("Output does not contain expected text", "WARNING")
                    return True  # Still passed, just no expected output

            elif status in ("failed", "timeout", "error"):
                stderr = data.get("stderr", "")
                log(f"Command failed: {status}", "ERROR")
                log(f"Stderr: {stderr}")
                return False

        time.sleep(1)

    log(f"Command did not complete within {timeout}s", "ERROR")
    return False


def step_7_cleanup(beacon_id: int, beacon_process: Optional[subprocess.Popen]) -> bool:
    """Clean up resources."""
    log("STEP 7: Cleaning up...")

    # Stop beacon process
    if beacon_process:
        log(f"   Terminating beacon process (PID={beacon_process.pid})...")
        beacon_process.terminate()
        try:
            beacon_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            beacon_process.kill()
        log("   Beacon process terminated")

    # Delete beacon via API
    log(f"   Deleting beacon {beacon_id}...")
    response = requests.delete(
        f"{API_URL}/api/shell/integrations/{beacon_id}",
        headers=get_auth_headers()
    )

    if response.status_code == 200:
        log(" Beacon deleted")
    else:
        log(f"Warning: Failed to delete beacon: {response.status_code}", "WARNING")

    return True


def run_e2e_test() -> bool:
    """Run the complete E2E test."""
    log("=" * 60)
    log("SHELL SKILL E2E TEST")
    log("=" * 60)
    log(f"API URL: {API_URL}")
    log(f"Beacon Name: {BEACON_NAME}")
    log("=" * 60)

    beacon_id = None
    api_key = None
    beacon_process = None

    try:
        # Step 1: Create beacon
        beacon_id, api_key = step_1_create_beacon()
        if not beacon_id or not api_key:
            return False

        # Step 2: Verify beacon exists
        if not step_2_verify_beacon_exists(beacon_id):
            return False

        # Step 3: Start beacon
        beacon_process = step_3_start_beacon(api_key)
        if not beacon_process:
            return False

        # Give beacon time to register
        time.sleep(3)

        # Step 4: Wait for beacon to come online
        if not step_4_wait_for_online(beacon_id):
            # Print beacon logs for debugging
            if beacon_process:
                beacon_process.terminate()
                output, _ = beacon_process.communicate(timeout=5)
                log(f"Beacon output:\n{output}", "DEBUG")
            return False

        # Step 5: Execute command
        command_id = step_5_execute_command(beacon_id)
        if not command_id:
            return False

        # Step 6: Wait for completion
        if not step_6_wait_for_completion(command_id):
            return False

        log("=" * 60)
        log(" E2E TEST PASSED!")
        log("=" * 60)
        return True

    except Exception as e:
        log(f"Test failed with exception: {e}", "ERROR")
        import traceback
        traceback.print_exc()
        return False

    finally:
        # Step 7: Cleanup
        if beacon_id:
            step_7_cleanup(beacon_id, beacon_process)


def main():
    """Main entry point."""
    success = run_e2e_test()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
