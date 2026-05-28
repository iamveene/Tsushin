#!/usr/bin/env bash
#
# Daily Docker disk maintenance for the Tsushin production host.
#
# WHY THIS EXISTS
#   The host previously ran only `docker image prune` from cron. That command
#   never touches the BuildKit *build cache*, so the cache grew unbounded to
#   ~262 GB, filled the disk to 100%, and broke a production deploy on
#   2026-05-28 ("not enough free space in /var/cache/apt/archives" during
#   `playwright install-deps`). This script keeps the image cleanup AND adds the
#   missing build-cache cap, with logging so future disk issues are debuggable.
#
# WHAT IT DOES
#   Every operation only touches UNUSED resources. Running containers, the
#   images they use, and named volumes are never affected:
#     1. Removes unused images older than the retention window (TSN_IMAGE_PRUNE_UNTIL).
#     2. Caps the BuildKit build cache to a fixed size (TSN_BUILD_CACHE_MAX) — the fix.
#     3. Logs before/after disk + `docker system df` for auditability.
#
#   It deliberately does NOT prune containers or volumes (data-loss risk):
#   runtime-created WhatsApp MCP helper containers and Postgres/app volumes must
#   survive.
#
# USAGE
#   Run by hand:   sudo /opt/code/tsushin/scripts/docker-disk-cleanup.sh
#   Scheduled via: /etc/cron.d/tsushin-docker-cleanup (see scripts/cron/).
#   Overridable env: TSN_CLEANUP_LOG, TSN_IMAGE_PRUNE_UNTIL, TSN_BUILD_CACHE_MAX.
#
# A single prune step exiting non-zero never aborts the whole run; the script
# logs the failure and continues, so a transient Docker hiccup can't leave the
# disk uncleaned.
set -uo pipefail

IMAGE_PRUNE_UNTIL="${TSN_IMAGE_PRUNE_UNTIL:-24h}"
BUILD_CACHE_MAX="${TSN_BUILD_CACHE_MAX:-10GB}"

log() {
  printf '%s %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*"
}

disk_summary() {
  # e.g. "29% used, 270G free" — robust to leading whitespace from df.
  df -h --output=pcent,avail / 2>/dev/null | tail -1 \
    | awk '{printf "%s used, %s free", $1, $2}'
}

run_step() {
  # run_step "<label>" <cmd...> — never let one failing prune abort the run.
  local label="$1"
  shift
  log "-> ${label}"
  log "   \$ $*"
  if "$@"; then
    log "   ok"
  else
    log "   WARN: step exited non-zero (continuing)"
  fi
}

main() {
  command -v docker >/dev/null 2>&1 || { log "ERROR: docker not found in PATH"; exit 1; }

  log "=== tsushin docker cleanup start ==="
  log "disk before: $(disk_summary)"
  log "docker df before:"
  docker system df 2>&1 || true

  run_step "image prune (unused images older than ${IMAGE_PRUNE_UNTIL})" \
    docker image prune -af --filter "until=${IMAGE_PRUNE_UNTIL}"

  run_step "build cache cap (max ${BUILD_CACHE_MAX})" \
    docker buildx prune -af --max-used-space="${BUILD_CACHE_MAX}"

  log "docker df after:"
  docker system df 2>&1 || true
  log "disk after:  $(disk_summary)"
  log "=== tsushin docker cleanup end ==="
}

main "$@"
