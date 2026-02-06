#!/usr/bin/env python3
"""
Complete WhatsApp MCP System Validation
Tests the entire ecosystem end-to-end
"""

import sys
import os
import time
import docker
import requests
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import WhatsAppMCPInstance, Agent
from services.mcp_container_manager import MCPContainerManager
from services.docker_network_utils import resolve_tsushin_network_name

DATABASE_PATH = "data/agent.db"
BACKEND_URL = "http://localhost:8081"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'
    BOLD = '\033[1m'

def print_section(title):
    print(f"\n{Colors.BLUE}{Colors.BOLD}{'='*80}{Colors.END}")
    print(f"{Colors.BLUE}{Colors.BOLD}{title}{Colors.END}")
    print(f"{Colors.BLUE}{Colors.BOLD}{'='*80}{Colors.END}\n")

def print_pass(msg):
    print(f"{Colors.GREEN}✅ PASS{Colors.END}: {msg}")

def print_fail(msg):
    print(f"{Colors.RED}❌ FAIL{Colors.END}: {msg}")

def print_warn(msg):
    print(f"{Colors.YELLOW}⚠️  WARN{Colors.END}: {msg}")

def print_info(msg):
    print(f"ℹ️  {msg}")

def get_db():
    engine = create_engine(f"sqlite:///{DATABASE_PATH}")
    Session = sessionmaker(bind=engine)
    return Session()

def validate_docker_environment():
    """Validate Docker is running and accessible"""
    print_section("1. DOCKER ENVIRONMENT")

    try:
        client = docker.from_env()
        print_pass("Docker client initialized")

        # Check Docker daemon
        client.ping()
        print_pass("Docker daemon responding")

        # Check for required network
        network_name = resolve_tsushin_network_name(client)
        networks = client.networks.list(names=[network_name])
        if networks:
            print_pass(f"Tsushin network exists ({network_name})")
        else:
            print_fail(f"Tsushin network missing ({network_name})")
            return False

        # Check for MCP images
        images = client.images.list()
        image_names = [tag for img in images for tag in img.tags]

        if any('tsushin/whatsapp-mcp' in name for name in image_names):
            print_pass("WhatsApp MCP image exists")
        else:
            print_fail("WhatsApp MCP image missing")
            return False

        if any('tsushin/tester-mcp' in name for name in image_names):
            print_pass("Tester MCP image exists")
        else:
            print_warn("Tester MCP image missing (optional)")

        return True

    except Exception as e:
        print_fail(f"Docker environment error: {e}")
        return False

def validate_database():
    """Validate database schema and data"""
    print_section("2. DATABASE VALIDATION")

    try:
        db = get_db()

        # Check tables exist
        from sqlalchemy import inspect
        engine = db.bind
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        required_tables = ['whatsapp_mcp_instance', 'agent', 'user', 'tenant']
        for table in required_tables:
            if table in tables:
                print_pass(f"Table '{table}' exists")
            else:
                print_fail(f"Table '{table}' missing")
                return False

        # Check MCP instances
        instances = db.query(WhatsAppMCPInstance).all()
        print_info(f"Found {len(instances)} MCP instances in database")

        for instance in instances:
            print_info(f"  Instance #{instance.id}: {instance.phone_number} ({instance.instance_type})")
            print_info(f"    Container: {instance.container_name}")
            print_info(f"    Port: {instance.mcp_port}")
            print_info(f"    Status: {instance.status}")

        # Check agents
        agents = db.query(Agent).all()
        print_info(f"Found {len(agents)} agents in database")

        db.close()
        return True

    except Exception as e:
        print_fail(f"Database validation error: {e}")
        return False

def validate_containers():
    """Validate Docker containers are running correctly"""
    print_section("3. CONTAINER VALIDATION")

    try:
        client = docker.from_env()
        db = get_db()

        instances = db.query(WhatsAppMCPInstance).all()

        if not instances:
            print_warn("No MCP instances in database")
            return True

        all_valid = True

        for instance in instances:
            print_info(f"\nValidating Instance #{instance.id}: {instance.phone_number}")

            # Check container exists
            try:
                container = client.containers.get(instance.container_id)
                print_pass(f"  Container exists: {container.name}")

                # Check container is running
                if container.status == 'running':
                    print_pass(f"  Container running")
                else:
                    print_fail(f"  Container not running: {container.status}")
                    all_valid = False

                # Check container name matches
                if container.name == instance.container_name:
                    print_pass(f"  Container name matches: {container.name}")
                else:
                    print_fail(f"  Container name mismatch: DB={instance.container_name}, Docker={container.name}")
                    all_valid = False

                # Check port mapping
                ports = container.ports
                expected_port = f"{instance.mcp_port}/tcp"
                if '8080/tcp' in ports and ports['8080/tcp']:
                    host_port = ports['8080/tcp'][0]['HostPort']
                    if host_port == str(instance.mcp_port):
                        print_pass(f"  Port mapping correct: {instance.mcp_port}")
                    else:
                        print_fail(f"  Port mapping mismatch: DB={instance.mcp_port}, Docker={host_port}")
                        all_valid = False
                else:
                    print_fail(f"  Port mapping missing")
                    all_valid = False

                # Check network
                networks = container.attrs['NetworkSettings']['Networks']
                network_name = resolve_tsushin_network_name(client)
                if network_name in networks:
                    print_pass(f"  Connected to tsushin network ({network_name})")
                else:
                    print_fail(f"  Not connected to tsushin network ({network_name})")
                    all_valid = False

            except docker.errors.NotFound:
                print_fail(f"  Container not found: {instance.container_id}")
                all_valid = False
            except Exception as e:
                print_fail(f"  Container validation error: {e}")
                all_valid = False

        db.close()
        return all_valid

    except Exception as e:
        print_fail(f"Container validation error: {e}")
        return False

def validate_mcp_health():
    """Validate MCP health endpoints"""
    print_section("4. MCP HEALTH ENDPOINTS")

    try:
        db = get_db()
        instances = db.query(WhatsAppMCPInstance).all()

        if not instances:
            print_warn("No MCP instances to check")
            return True

        all_healthy = True

        for instance in instances:
            print_info(f"\nChecking Instance #{instance.id}: {instance.phone_number}")

            try:
                # Check direct MCP health endpoint
                url = f"http://localhost:{instance.mcp_port}/api/health"
                response = requests.get(url, timeout=5)

                if response.status_code == 200:
                    print_pass(f"  Health endpoint responding")

                    health = response.json()

                    # Check for new enhanced fields
                    expected_fields = [
                        'status', 'connected', 'authenticated',
                        'needs_reauth', 'is_reconnecting', 'reconnect_attempts',
                        'session_age_sec', 'last_activity_sec'
                    ]

                    missing_fields = [f for f in expected_fields if f not in health]
                    if missing_fields:
                        print_fail(f"  Missing health fields: {missing_fields}")
                        all_healthy = False
                    else:
                        print_pass(f"  All enhanced health fields present")

                    # Print health status
                    print_info(f"    Status: {health.get('status')}")
                    print_info(f"    Authenticated: {health.get('authenticated')}")
                    print_info(f"    Connected: {health.get('connected')}")
                    print_info(f"    Reconnect Attempts: {health.get('reconnect_attempts')}")
                    print_info(f"    Session Age: {health.get('session_age_sec')}s")
                    print_info(f"    Last Activity: {health.get('last_activity_sec')}s ago")

                    if health.get('needs_reauth'):
                        print_warn(f"  Needs re-authentication (QR scan required)")

                    if not health.get('authenticated'):
                        print_warn(f"  Not authenticated")
                        all_healthy = False

                else:
                    print_fail(f"  Health endpoint returned {response.status_code}")
                    all_healthy = False

            except requests.RequestException as e:
                print_fail(f"  Health endpoint unreachable: {e}")
                all_healthy = False

        db.close()
        return all_healthy

    except Exception as e:
        print_fail(f"MCP health validation error: {e}")
        return False

def validate_session_files():
    """Validate session files exist"""
    print_section("5. SESSION FILE VALIDATION")

    try:
        db = get_db()
        instances = db.query(WhatsAppMCPInstance).all()

        if not instances:
            print_warn("No MCP instances to check")
            return True

        all_valid = True

        for instance in instances:
            print_info(f"\nInstance #{instance.id}: {instance.phone_number}")

            # Get session directory (convert container path to host path)
            session_dir = instance.session_data_path.replace('/app/data/', 'data/')
            session_path = Path(session_dir)

            print_info(f"  Session dir: {session_path}")

            if session_path.exists():
                print_pass(f"  Session directory exists")

                # Check for whatsapp.db
                whatsapp_db = session_path / "whatsapp.db"
                if whatsapp_db.exists():
                    size = whatsapp_db.stat().st_size
                    print_pass(f"  whatsapp.db exists ({size:,} bytes)")
                else:
                    print_fail(f"  whatsapp.db missing")
                    all_valid = False

                    # Check for backups
                    backups = list(session_path.glob("whatsapp.db.backup.*"))
                    if backups:
                        print_info(f"  Found {len(backups)} backup(s)")
                        latest = max(backups, key=lambda p: p.stat().st_mtime)
                        print_info(f"  Latest backup: {latest.name}")

                # Check for messages.db
                messages_db = session_path / "messages.db"
                if messages_db.exists():
                    size = messages_db.stat().st_size
                    print_pass(f"  messages.db exists ({size:,} bytes)")
                else:
                    print_warn(f"  messages.db missing (will be created)")

            else:
                print_fail(f"  Session directory missing")
                all_valid = False

        db.close()
        return all_valid

    except Exception as e:
        print_fail(f"Session file validation error: {e}")
        return False

def validate_backend_management():
    """Validate Python backend can manage containers"""
    print_section("6. BACKEND MANAGEMENT FUNCTIONS")

    try:
        manager = MCPContainerManager()
        db = get_db()

        instances = db.query(WhatsAppMCPInstance).all()

        if not instances:
            print_warn("No MCP instances to test management")
            return True

        # Test health check function
        print_info("Testing health check function...")
        for instance in instances:
            try:
                health = manager.health_check(instance)
                print_pass(f"  Instance #{instance.id} health check works")
            except Exception as e:
                print_fail(f"  Instance #{instance.id} health check failed: {e}")
                return False

        # Test QR code retrieval
        print_info("Testing QR code retrieval...")
        for instance in instances:
            try:
                qr = manager.get_qr_code(instance)
                if qr:
                    print_info(f"  Instance #{instance.id} has QR code available")
                else:
                    print_info(f"  Instance #{instance.id} QR code not needed (authenticated)")
            except Exception as e:
                print_fail(f"  Instance #{instance.id} QR code retrieval failed: {e}")
                return False

        db.close()
        print_pass("All backend management functions working")
        return True

    except Exception as e:
        print_fail(f"Backend management validation error: {e}")
        return False

def validate_frontend_api():
    """Validate frontend can access backend API"""
    print_section("7. FRONTEND API ACCESS")

    try:
        # Note: These will fail without auth token, but should get 401 not 404

        # Test MCP instances endpoint
        print_info("Testing /api/mcp/instances/ endpoint...")
        response = requests.get(f"{BACKEND_URL}/api/mcp/instances/")
        if response.status_code == 401:
            print_pass("Endpoint exists (needs authentication)")
        elif response.status_code == 404:
            print_fail("Endpoint not found (404)")
            return False
        else:
            print_info(f"  Response: {response.status_code}")

        # Test MCP create endpoint
        print_info("Testing POST /api/mcp/instances/ endpoint...")
        response = requests.post(
            f"{BACKEND_URL}/api/mcp/instances/",
            json={"phone_number": "+test", "instance_type": "agent"}
        )
        if response.status_code == 401:
            print_pass("Endpoint exists (needs authentication)")
        elif response.status_code == 404:
            print_fail("Endpoint not found (404)")
            return False
        else:
            print_info(f"  Response: {response.status_code}")

        return True

    except Exception as e:
        print_fail(f"Frontend API validation error: {e}")
        return False

def validate_watcher_integration():
    """Validate watcher can access MCP databases"""
    print_section("8. WATCHER INTEGRATION")

    try:
        db = get_db()
        instances = db.query(WhatsAppMCPInstance).filter_by(instance_type='agent').all()

        if not instances:
            print_warn("No agent instances to check")
            return True

        all_valid = True

        for instance in instances:
            print_info(f"\nInstance #{instance.id}: {instance.phone_number}")

            # Check messages.db path
            messages_db = instance.messages_db_path
            print_info(f"  Messages DB path: {messages_db}")

            # Convert container path to host path for checking
            host_path = messages_db.replace('/app/data/', 'data/')
            db_path = Path(host_path)

            if db_path.exists():
                print_pass(f"  Messages DB accessible")

                # Try to connect to it
                try:
                    import sqlite3
                    conn = sqlite3.connect(str(db_path))
                    cursor = conn.cursor()

                    # Check for messages table
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='messages'")
                    if cursor.fetchone():
                        print_pass(f"  Messages table exists")

                        # Count messages
                        cursor.execute("SELECT COUNT(*) FROM messages")
                        count = cursor.fetchone()[0]
                        print_info(f"    Message count: {count:,}")
                    else:
                        print_warn(f"  Messages table not created yet")

                    conn.close()
                except Exception as e:
                    print_fail(f"  Cannot access messages DB: {e}")
                    all_valid = False
            else:
                print_fail(f"  Messages DB not found at {db_path}")
                all_valid = False

        db.close()
        return all_valid

    except Exception as e:
        print_fail(f"Watcher integration validation error: {e}")
        return False

def validate_keepalive():
    """Validate keepalive mechanism is working"""
    print_section("9. KEEPALIVE MECHANISM")

    try:
        db = get_db()
        instances = db.query(WhatsAppMCPInstance).all()

        if not instances:
            print_warn("No MCP instances to check")
            return True

        all_valid = True

        for instance in instances:
            print_info(f"\nInstance #{instance.id}: {instance.phone_number}")

            try:
                # Get health status
                url = f"http://localhost:{instance.mcp_port}/api/health"
                response = requests.get(url, timeout=5)

                if response.status_code == 200:
                    health = response.json()
                    last_activity = health.get('last_activity_sec', 999999)

                    # Keepalive should update every 30s, so activity should be < 35s
                    if last_activity < 35:
                        print_pass(f"  Keepalive active (last activity: {last_activity}s ago)")
                    else:
                        print_fail(f"  Keepalive not working (last activity: {last_activity}s ago)")
                        all_valid = False

                    # Check for keepalive in logs
                    client = docker.from_env()
                    container = client.containers.get(instance.container_id)
                    logs = container.logs(tail=50).decode('utf-8', errors='ignore')

                    if 'Keepalive mechanism started' in logs:
                        print_pass(f"  Keepalive started in logs")
                    else:
                        print_warn(f"  Keepalive start not found in recent logs")

                else:
                    print_fail(f"  Cannot check keepalive (health endpoint failed)")
                    all_valid = False

            except Exception as e:
                print_fail(f"  Keepalive check failed: {e}")
                all_valid = False

        db.close()
        return all_valid

    except Exception as e:
        print_fail(f"Keepalive validation error: {e}")
        return False

def main():
    """Run complete system validation"""
    print(f"\n{Colors.BOLD}{'='*80}{Colors.END}")
    print(f"{Colors.BOLD}WhatsApp MCP COMPLETE SYSTEM VALIDATION{Colors.END}")
    print(f"{Colors.BOLD}{'='*80}{Colors.END}")

    results = []

    # Run all validations
    results.append(("Docker Environment", validate_docker_environment()))
    results.append(("Database", validate_database()))
    results.append(("Containers", validate_containers()))
    results.append(("MCP Health", validate_mcp_health()))
    results.append(("Session Files", validate_session_files()))
    results.append(("Backend Management", validate_backend_management()))
    results.append(("Frontend API", validate_frontend_api()))
    results.append(("Watcher Integration", validate_watcher_integration()))
    results.append(("Keepalive Mechanism", validate_keepalive()))

    # Print summary
    print_section("VALIDATION SUMMARY")

    for name, passed in results:
        if passed:
            print_pass(f"{name:30} PASS")
        else:
            print_fail(f"{name:30} FAIL")

    print()
    passed_count = sum(1 for _, p in results if p)
    total = len(results)
    percentage = (passed_count / total * 100) if total > 0 else 0

    print(f"Total: {passed_count}/{total} validations passed ({percentage:.1f}%)")
    print()

    if passed_count == total:
        print(f"{Colors.GREEN}{Colors.BOLD}🎉 ALL VALIDATIONS PASSED{Colors.END}")
        print()
        return 0
    else:
        print(f"{Colors.RED}{Colors.BOLD}⚠️  SOME VALIDATIONS FAILED{Colors.END}")
        print()
        print("Please review failures above and fix before deployment.")
        print()
        return 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nValidation interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n{Colors.RED}Validation failed with error: {e}{Colors.END}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
