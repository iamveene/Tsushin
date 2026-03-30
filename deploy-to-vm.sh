#!/usr/bin/env bash
# deploy-to-vm.sh — Rsync Tsushin codebase to Parallels Ubuntu VM
# Usage: bash deploy-to-vm.sh [user@host] [remote_path]
set -euo pipefail

REMOTE_HOST="${1:-parallels@10.211.55.5}"
REMOTE_PATH="${2:-~/tsushin}"
LOCAL_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC}   $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
die()     { echo -e "${RED}[FAIL]${NC} $*" >&2; exit 1; }

echo "================================================================"
echo "  Tsushin VM Deployment Script"
echo "  Target: ${REMOTE_HOST}:${REMOTE_PATH}"
echo "================================================================"
echo

# ── Step 1: SSH connectivity ──────────────────────────────────────────
info "Verifying SSH connectivity to ${REMOTE_HOST}..."
if ! ssh -o ConnectTimeout=10 -o BatchMode=yes "${REMOTE_HOST}" 'echo connected' &>/dev/null; then
    die "Cannot reach ${REMOTE_HOST} via SSH. Check your VPN/network and SSH key auth."
fi
success "SSH connection OK"

# ── Step 2: Docker available on remote ───────────────────────────────
info "Verifying Docker is available on remote..."
if ! ssh "${REMOTE_HOST}" 'docker --version' &>/dev/null; then
    die "Docker not found on ${REMOTE_HOST}. Install Docker first."
fi
DOCKER_VER=$(ssh "${REMOTE_HOST}" 'docker --version')
success "Remote Docker: ${DOCKER_VER}"

# ── Step 3: Install Python3 prereqs ──────────────────────────────────
info "Installing Python3 prereqs on remote (requests, cryptography)..."
ssh "${REMOTE_HOST}" 'sudo apt-get install -y python3-pip python3-cryptography python3-requests 2>&1 | tail -3 || pip3 install requests cryptography 2>&1 | tail -3'
success "Python3 prereqs ready"

# ── Step 4: Ensure remote directory exists ───────────────────────────
info "Ensuring remote directory ${REMOTE_PATH} exists..."
ssh "${REMOTE_HOST}" "mkdir -p ${REMOTE_PATH}"
success "Remote directory ready"

# ── Step 5: Rsync codebase ───────────────────────────────────────────
info "Rsyncing codebase to ${REMOTE_HOST}:${REMOTE_PATH}..."
rsync -avz --progress \
    --exclude='.git/' \
    --exclude='.private/' \
    --exclude='backend/data/' \
    --exclude='node_modules/' \
    --exclude='frontend/.next/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    --exclude='logs/' \
    --exclude='backups/' \
    --exclude='.env' \
    --exclude='.DS_Store' \
    --exclude='backend/venv/' \
    --exclude='backend/dev_tests/' \
    --exclude='test-screenshots/' \
    --exclude='.claude/' \
    "${LOCAL_PATH}/" \
    "${REMOTE_HOST}:${REMOTE_PATH}/"

success "Rsync complete"

# ── Step 6: Make scripts executable ──────────────────────────────────
info "Setting executable permissions on scripts..."
ssh "${REMOTE_HOST}" "chmod +x ${REMOTE_PATH}/install.py ${REMOTE_PATH}/deploy-to-vm.sh 2>/dev/null || true"
success "Permissions set"

# ── Done ─────────────────────────────────────────────────────────────
echo
echo "================================================================"
echo -e "  ${GREEN}Deployment complete!${NC}"
echo "================================================================"
echo
echo "  Next steps:"
echo "    1. SSH into the VM:"
echo "       ssh ${REMOTE_HOST}"
echo
echo "    2. Run the installer:"
echo "       cd ${REMOTE_PATH} && sudo python3 install.py"
echo
echo "    3. When prompted, provide:"
echo "       - AI provider API key (Gemini recommended)"
echo "       - Ports: 8081 (backend), 3030 (frontend)"
echo "       - Access type: remote  →  IP: 10.211.55.5"
echo "       - SSL: disabled (option 1)"
echo "       - Tenant name, global admin credentials, tenant admin credentials"
echo "       - Passwords must be 8+ characters"
echo
echo "    4. After install completes, verify:"
echo "       curl http://10.211.55.5:8081/api/health"
echo "       curl http://10.211.55.5:8081/api/readiness"
echo
