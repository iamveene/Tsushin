#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REMOTE_USER="${REMOTE_USER:-parallels}"
REMOTE_HOST="${REMOTE_HOST:-10.211.55.5}"
REMOTE_PATH="${REMOTE_PATH:-~/tsushin}"
SSH_TARGET="${REMOTE_USER}@${REMOTE_HOST}"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=10)

info() {
  printf '[deploy] %s\n' "$1"
}

fail() {
  printf '[deploy] ERROR: %s\n' "$1" >&2
  exit 1
}

require_local_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Required local command not found: $1"
}

check_remote_python_prereqs() {
  ssh "${SSH_OPTS[@]}" "$SSH_TARGET" \
    'python3 -c "import requests, cryptography" >/dev/null 2>&1'
}

install_remote_python_prereqs() {
  info "Installing remote Python prerequisites with pip3 --user"
  ssh "${SSH_OPTS[@]}" "$SSH_TARGET" '
    command -v pip3 >/dev/null 2>&1 || {
      echo "pip3 is required on the remote host to install requests/cryptography." >&2
      exit 1
    }
    python3 -m pip install --user --break-system-packages requests cryptography
  '
}

main() {
  require_local_cmd ssh
  require_local_cmd rsync
  require_local_cmd git

  [[ -f "$REPO_ROOT/install.py" ]] || fail "Run this script from the repository root."

  local branch commit
  branch="$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD)"
  commit="$(git -C "$REPO_ROOT" rev-parse --short HEAD)"

  info "Source: $REPO_ROOT"
  info "Branch: $branch ($commit)"
  info "Target: $SSH_TARGET:$REMOTE_PATH"

  info "Verifying SSH connectivity"
  ssh "${SSH_OPTS[@]}" "$SSH_TARGET" 'printf "ssh-ok\n"' >/dev/null

  info "Verifying remote Docker availability"
  ssh "${SSH_OPTS[@]}" "$SSH_TARGET" 'docker --version && docker compose version'

  info "Checking remote Python prerequisites"
  if check_remote_python_prereqs; then
    info "Remote requests/cryptography already available"
  else
    install_remote_python_prereqs
  fi

  info "Ensuring remote path exists"
  ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "mkdir -p $REMOTE_PATH"

  info "Syncing repository to the VM with rsync"
  rsync -az --progress \
    --exclude='.git/' \
    --exclude='.private/' \
    --exclude='backend/data/' \
    --exclude='backend/venv/' \
    --exclude='node_modules/' \
    --exclude='frontend/.next/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='logs/' \
    --exclude='backups/' \
    --exclude='.env' \
    --exclude='.DS_Store' \
    "$REPO_ROOT/" "$SSH_TARGET:$REMOTE_PATH/"

  cat <<EOF

[deploy] Sync complete.
[deploy] Next steps:
  1. ssh $SSH_TARGET
  2. cd $REMOTE_PATH
  3. sudo python3 install.py

[deploy] Current develop behavior:
  - install.py handles infrastructure only
  - create the tenant admin and AI provider key(s) in http://$REMOTE_HOST:3030/setup
  - capture the generated global admin credentials from the setup completion screen

EOF
}

main "$@"
