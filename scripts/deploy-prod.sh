#!/usr/bin/env bash
set -euo pipefail

# Deploy Tsushin production from the release branch.
#
# Default flow:
#   1. validate this checkout is on main and pushed
#   2. SSH to the production checkout
#   3. git pull --ff-only on the production host
#   4. rebuild only changed compose services, without docker-compose down
#   5. verify local container health and the public Cloudflare URL
#
# No secrets are stored here. Provide SSH credentials through your normal SSH
# agent or, if needed for an interactive one-off, DEPLOY_SSH_PASSWORD.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

DEPLOY_HOST="${DEPLOY_HOST:-hunter.archsec.io}"
DEPLOY_USER="${DEPLOY_USER:-root}"
DEPLOY_SSH_PORT="${DEPLOY_SSH_PORT:-22}"
DEPLOY_REMOTE_DIR="${DEPLOY_REMOTE_DIR:-/opt/code/tsushin}"
DEPLOY_GIT_REMOTE="${DEPLOY_GIT_REMOTE:-origin}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"
DEPLOY_PUBLIC_URL="${DEPLOY_PUBLIC_URL:-https://tsushin.archsec.io}"

DEPLOY_ALLOW_NON_MAIN="${DEPLOY_ALLOW_NON_MAIN:-0}"
DEPLOY_ALLOW_DIRTY="${DEPLOY_ALLOW_DIRTY:-0}"
DEPLOY_REQUIRE_PUSH="${DEPLOY_REQUIRE_PUSH:-1}"
DEPLOY_FORCE_REBUILD="${DEPLOY_FORCE_REBUILD:-0}"
DEPLOY_SERVICES="${DEPLOY_SERVICES:-auto}"
DEPLOY_SKIP_PUBLIC_CHECK="${DEPLOY_SKIP_PUBLIC_CHECK:-0}"
DEPLOY_SKIP_ALLOWLIST_STATUS="${DEPLOY_SKIP_ALLOWLIST_STATUS:-0}"
DEPLOY_PROMPT_PASSWORD="${DEPLOY_PROMPT_PASSWORD:-1}"

CF_ALLOWLIST_SCRIPT="${CF_ALLOWLIST_SCRIPT:-/Users/vinicios/code/cloudflare/cf-allowlist.sh}"

SSH_OPTS=(
  -p "$DEPLOY_SSH_PORT"
  -o StrictHostKeyChecking=accept-new
  -o ServerAliveInterval=15
  -o ServerAliveCountMax=4
)

log() {
  printf '\n>> %s\n' "$*"
}

warn() {
  printf 'WARN: %s\n' "$*" >&2
}

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"
}

shell_quote() {
  printf '%q' "$1"
}

maybe_prompt_password() {
  if [[ -z "${DEPLOY_SSH_PASSWORD:-}" && "$DEPLOY_PROMPT_PASSWORD" == "1" && -t 0 ]]; then
    read -r -s -p "SSH password for ${DEPLOY_USER}@${DEPLOY_HOST}: " DEPLOY_SSH_PASSWORD
    printf '\n'
  fi

  if [[ -n "${DEPLOY_SSH_PASSWORD:-}" ]]; then
    require_command sshpass
  fi
}

run_ssh() {
  if [[ -n "${DEPLOY_SSH_PASSWORD:-}" ]]; then
    SSHPASS="$DEPLOY_SSH_PASSWORD" sshpass -e ssh "${SSH_OPTS[@]}" "$DEPLOY_USER@$DEPLOY_HOST" "$@"
  else
    ssh "${SSH_OPTS[@]}" "$DEPLOY_USER@$DEPLOY_HOST" "$@"
  fi
}

http_check() {
  local url="$1"
  local label="$2"
  local attempts="${3:-18}"
  local delay_seconds="${4:-5}"

  for ((attempt = 1; attempt <= attempts; attempt += 1)); do
    if curl -fsS --max-time 20 -o /dev/null "$url"; then
      printf 'OK: %s (%s)\n' "$label" "$url"
      return 0
    fi
    printf 'Waiting for %s (%s/%s)\n' "$label" "$attempt" "$attempts"
    sleep "$delay_seconds"
  done

  fail "Could not reach ${label}: ${url}"
}

validate_release_branch() {
  if [[ "$DEPLOY_BRANCH" != "main" && "$DEPLOY_ALLOW_NON_MAIN" != "1" ]]; then
    fail "Production deploys must target main. Set DEPLOY_ALLOW_NON_MAIN=1 only for an explicit emergency override."
  fi
}

run_cloudflare_allowlist_status() {
  if [[ "$DEPLOY_SKIP_ALLOWLIST_STATUS" == "1" ]]; then
    log "Skipping Cloudflare allowlist status check"
    return 0
  fi

  if [[ ! -x "$CF_ALLOWLIST_SCRIPT" ]]; then
    warn "Cloudflare allowlist helper is not executable at $CF_ALLOWLIST_SCRIPT"
    warn "Use: $CF_ALLOWLIST_SCRIPT status | current-ip | add-host <host> | add-ip <ip-or-cidr>"
    return 0
  fi

  log "Checking Cloudflare allowlist status"
  "$CF_ALLOWLIST_SCRIPT" status || fail "Cloudflare allowlist status failed. Use current-ip/add-host/add-ip before deploying."
}

local_preflight() {
  require_command git
  require_command ssh
  require_command curl
  maybe_prompt_password
  validate_release_branch

  cd "$REPO_DIR"

  local current_branch
  current_branch="$(git rev-parse --abbrev-ref HEAD)"
  if [[ "$current_branch" != "$DEPLOY_BRANCH" ]]; then
    fail "Current branch is ${current_branch}, expected ${DEPLOY_BRANCH}. Merge develop via PR, check out main, then deploy."
  fi

  if [[ "$DEPLOY_ALLOW_DIRTY" != "1" ]]; then
    git diff --quiet || fail "Working tree has unstaged changes. Commit or set DEPLOY_ALLOW_DIRTY=1."
    git diff --cached --quiet || fail "Working tree has staged changes. Commit or set DEPLOY_ALLOW_DIRTY=1."
  fi

  if [[ "$DEPLOY_REQUIRE_PUSH" == "1" ]]; then
    git fetch --quiet "$DEPLOY_GIT_REMOTE" "$DEPLOY_BRANCH"
    local local_rev remote_rev
    local_rev="$(git rev-parse HEAD)"
    remote_rev="$(git rev-parse "${DEPLOY_GIT_REMOTE}/${DEPLOY_BRANCH}")"
    if [[ "$local_rev" != "$remote_rev" ]]; then
      fail "Local HEAD ${local_rev} does not match ${DEPLOY_GIT_REMOTE}/${DEPLOY_BRANCH} ${remote_rev}. Push or set DEPLOY_REQUIRE_PUSH=0."
    fi
  fi

  run_cloudflare_allowlist_status
}

remote_pull_build_and_verify() {
  local remote_dir_q git_remote_q branch_q allow_non_main_q force_rebuild_q services_q
  remote_dir_q="$(shell_quote "$DEPLOY_REMOTE_DIR")"
  git_remote_q="$(shell_quote "$DEPLOY_GIT_REMOTE")"
  branch_q="$(shell_quote "$DEPLOY_BRANCH")"
  allow_non_main_q="$(shell_quote "$DEPLOY_ALLOW_NON_MAIN")"
  force_rebuild_q="$(shell_quote "$DEPLOY_FORCE_REBUILD")"
  services_q="$(shell_quote "$DEPLOY_SERVICES")"

  log "Pulling and rebuilding production checkout on ${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_REMOTE_DIR}"
  run_ssh "cd $remote_dir_q && DEPLOY_GIT_REMOTE=$git_remote_q DEPLOY_BRANCH=$branch_q DEPLOY_ALLOW_NON_MAIN=$allow_non_main_q DEPLOY_FORCE_REBUILD=$force_rebuild_q DEPLOY_SERVICES=$services_q bash -s" <<'REMOTE'
set -euo pipefail

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

get_env_value() {
  local key="$1"
  local line value
  [[ -f .env ]] || return 0
  line="$(grep -E "^${key}=" .env | tail -n 1 || true)"
  [[ -n "$line" ]] || return 0
  value="${line#*=}"
  value="${value%\"}"
  value="${value#\"}"
  printf '%s' "$value"
}

select_compose() {
  if command -v docker-compose >/dev/null 2>&1; then
    COMPOSE=(docker-compose)
  elif docker compose version >/dev/null 2>&1; then
    COMPOSE=(docker compose)
  else
    fail "Neither docker-compose nor docker compose is available"
  fi
}

compose() {
  "${COMPOSE[@]}" "$@"
}

service_in_list() {
  local needle="$1"
  shift
  local item
  for item in "$@"; do
    [[ "$item" == "$needle" ]] && return 0
  done
  return 1
}

add_service() {
  local service="$1"
  shift
  local -n target_list="$1"
  service_in_list "$service" "${target_list[@]:-}" || target_list+=("$service")
}

detect_services() {
  local before="$1"
  local after="$2"
  build_services=()
  restart_services=()

  if [[ "$DEPLOY_SERVICES" != "auto" ]]; then
    read -r -a requested_services <<< "$DEPLOY_SERVICES"
    local service
    for service in "${requested_services[@]}"; do
      case "$service" in
        backend|frontend) add_service "$service" build_services ;;
        proxy|postgres|docker-socket-proxy) add_service "$service" restart_services ;;
        *) fail "Unsupported DEPLOY_SERVICES entry: $service" ;;
      esac
    done
    return 0
  fi

  if [[ "$DEPLOY_FORCE_REBUILD" == "1" || "$before" == "$after" ]]; then
    [[ "$DEPLOY_FORCE_REBUILD" == "1" ]] || return 0
    add_service backend build_services
    add_service frontend build_services
    return 0
  fi

  local path
  while IFS= read -r path; do
    case "$path" in
      backend/*|backend)
        add_service backend build_services
        ;;
      frontend/*|frontend)
        add_service frontend build_services
        ;;
      docker-compose.yml|docker-compose.*.yml|install.py|proxy/*|proxy)
        add_service backend build_services
        add_service frontend build_services
        add_service proxy restart_services
        ;;
    esac
  done < <(git diff --name-only "$before" "$after")
}

wait_for_container() {
  local container="$1"
  local attempts="${2:-60}"
  local status

  for ((attempt = 1; attempt <= attempts; attempt += 1)); do
    status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container" 2>/dev/null || true)"
    if [[ "$status" == "healthy" || "$status" == "running" ]]; then
      printf 'OK: %s is %s\n' "$container" "$status"
      return 0
    fi
    printf 'Waiting for %s (%s/%s, status=%s)\n' "$container" "$attempt" "$attempts" "${status:-missing}"
    sleep 5
  done

  docker ps -a --filter "name=$container"
  fail "$container did not become healthy"
}

wait_for_http() {
  local url="$1"
  local label="$2"
  local attempts="${3:-24}"

  for ((attempt = 1; attempt <= attempts; attempt += 1)); do
    if curl -fsS --max-time 15 -o /dev/null "$url"; then
      printf 'OK: %s (%s)\n' "$label" "$url"
      return 0
    fi
    printf 'Waiting for %s (%s/%s)\n' "$label" "$attempt" "$attempts"
    sleep 5
  done

  fail "Could not reach ${label}: ${url}"
}

[[ "$DEPLOY_BRANCH" == "main" || "$DEPLOY_ALLOW_NON_MAIN" == "1" ]] || fail "Remote deploy branch must be main unless DEPLOY_ALLOW_NON_MAIN=1"
[[ -d .git ]] || fail "$(pwd) is not a git checkout"
[[ -f .env ]] || fail "Remote .env is missing in $(pwd). Keep production secrets on the host and rerun."
command -v git >/dev/null 2>&1 || fail "git is required on the production host"
command -v docker >/dev/null 2>&1 || fail "docker is required on the production host"
select_compose

before="$(git rev-parse HEAD)"
git fetch "$DEPLOY_GIT_REMOTE" "$DEPLOY_BRANCH"
git checkout "$DEPLOY_BRANCH"
git pull --ff-only "$DEPLOY_GIT_REMOTE" "$DEPLOY_BRANCH"
after="$(git rev-parse HEAD)"

printf 'Deploy revision: %s -> %s\n' "$before" "$after"
detect_services "$before" "$after"

docker network inspect tsushin-network >/dev/null 2>&1 || docker network create tsushin-network >/dev/null

if ((${#build_services[@]} > 0)); then
  printf 'Rebuilding services: %s\n' "${build_services[*]}"
  compose build --no-cache "${build_services[@]}"
  compose up -d "${build_services[@]}"
else
  printf 'No backend/frontend rebuild needed for this revision.\n'
fi

base_services=(postgres docker-socket-proxy backend frontend proxy)
up_services=("${base_services[@]}")
for service in "${restart_services[@]:-}"; do
  add_service "$service" up_services
done

compose up -d "${up_services[@]}"
compose ps

stack_name="$(get_env_value TSN_STACK_NAME)"
stack_name="${stack_name:-tsushin}"
backend_port="$(get_env_value TSN_APP_PORT)"
backend_port="${backend_port:-8081}"
frontend_port="$(get_env_value FRONTEND_PORT)"
frontend_port="${frontend_port:-3030}"

wait_for_container "${stack_name}-postgres"
wait_for_container "${stack_name}-docker-proxy"
wait_for_container "${stack_name}-backend"
wait_for_container "${stack_name}-frontend"
wait_for_container "${stack_name}-proxy"

wait_for_http "http://127.0.0.1:${backend_port}/api/health" "server-local API health"
wait_for_http "http://127.0.0.1:${frontend_port}/auth/login" "server-local login page"
REMOTE
}

verify_public_url() {
  if [[ "$DEPLOY_SKIP_PUBLIC_CHECK" == "1" ]]; then
    log "Skipping public URL verification"
    return 0
  fi

  local public_base="${DEPLOY_PUBLIC_URL%/}"
  log "Verifying public Cloudflare route ${public_base}"
  http_check "${public_base}/api/health" "public API health"
  http_check "${public_base}/auth/login" "public login page"
}

main() {
  log "Tsushin production deploy target: ${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_REMOTE_DIR}"
  local_preflight
  remote_pull_build_and_verify
  verify_public_url
  log "Deployment complete. Run browser automation against ${DEPLOY_PUBLIC_URL} before calling production verified."
}

main "$@"
