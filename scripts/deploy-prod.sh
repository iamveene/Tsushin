#!/usr/bin/env bash
set -Eeuo pipefail

log() {
  printf '[deploy-prod] %s\n' "$*"
}

die() {
  printf '[deploy-prod] ERROR: %s\n' "$*" >&2
  exit 1
}

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/.." && pwd)"
config_file="${TSUSHIN_DEPLOY_CONFIG:-${repo_root}/.private/deploy-prod.env}"

if [[ -f "${config_file}" ]]; then
  # shellcheck source=/dev/null
  source "${config_file}"
fi

cd "${repo_root}"

local_branch="$(git rev-parse --abbrev-ref HEAD)"
[[ "${local_branch}" == "main" ]] || die "production deploys must run from main; current branch is ${local_branch}"

git diff --quiet || die "working tree has unstaged changes"
git diff --cached --quiet || die "working tree has staged changes"
[[ -z "$(git ls-files --others --exclude-standard)" ]] || die "working tree has untracked files"

ssh_target="${TSUSHIN_PROD_SSH_TARGET:-${PROD_SSH_TARGET:-}}"
[[ -n "${ssh_target}" ]] || die "set TSUSHIN_PROD_SSH_TARGET, or create ${config_file}"

prod_path="${TSUSHIN_PROD_PATH:-/opt/code/tsushin}"
prod_branch="${TSUSHIN_PROD_BRANCH:-main}"
public_url="${TSUSHIN_PUBLIC_URL:-https://tsushin.archsec.io}"
ssh_opts="${TSUSHIN_PROD_SSH_OPTS:-}"

log "deploying ${prod_branch} to ${ssh_target}:${prod_path}"
log "public verification URL: ${public_url}"

# shellcheck disable=SC2086
ssh ${ssh_opts} "${ssh_target}" \
  "TSUSHIN_PROD_PATH=$(printf '%q' "${prod_path}") TSUSHIN_PROD_BRANCH=$(printf '%q' "${prod_branch}") TSUSHIN_PUBLIC_URL=$(printf '%q' "${public_url}") bash -s" <<'REMOTE'
set -Eeuo pipefail

log() {
  printf '[deploy-prod:remote] %s\n' "$*"
}

die() {
  printf '[deploy-prod:remote] ERROR: %s\n' "$*" >&2
  exit 1
}

compose() {
  if command -v docker-compose >/dev/null 2>&1; then
    docker-compose "$@"
  else
    docker compose "$@"
  fi
}

cd "${TSUSHIN_PROD_PATH}"

remote_branch="$(git rev-parse --abbrev-ref HEAD)"
[[ "${remote_branch}" == "${TSUSHIN_PROD_BRANCH}" ]] || die "remote checkout is on ${remote_branch}, expected ${TSUSHIN_PROD_BRANCH}"

git diff --quiet || die "remote working tree has unstaged changes"
git diff --cached --quiet || die "remote working tree has staged changes"
[[ -z "$(git ls-files --others --exclude-standard)" ]] || die "remote working tree has untracked files"

log "fast-forwarding ${TSUSHIN_PROD_BRANCH}"
git fetch --prune origin "${TSUSHIN_PROD_BRANCH}"
git pull --ff-only origin "${TSUSHIN_PROD_BRANCH}"

log "rebuilding backend and frontend without docker-compose down"
if ! compose up -d --build --no-cache backend frontend; then
  log "compose up --no-cache is unavailable; falling back to build --no-cache then up"
  compose build --no-cache backend frontend
  compose up -d backend frontend
fi

wait_for_service() {
  local service="$1"
  local ids id status attempt

  ids="$(compose ps -q "${service}")"
  [[ -n "${ids}" ]] || die "no container id returned for ${service}"

  for id in ${ids}; do
    for attempt in $(seq 1 60); do
      status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${id}")"
      case "${status}" in
        healthy|running)
          log "${service} ${id} is ${status}"
          break
          ;;
        unhealthy|exited|dead)
          die "${service} ${id} is ${status}"
          ;;
      esac

      if [[ "${attempt}" == "60" ]]; then
        die "${service} ${id} did not become healthy/running; last status=${status}"
      fi

      sleep 2
    done
  done
}

wait_for_service backend
wait_for_service frontend

log "checking public health endpoint"
curl -fsS --max-time 20 "${TSUSHIN_PUBLIC_URL%/}/api/health" >/tmp/tsushin-prod-health.json
log "public health OK: $(cat /tmp/tsushin-prod-health.json)"
REMOTE

log "production deploy completed"
