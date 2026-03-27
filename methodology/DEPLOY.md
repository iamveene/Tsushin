# Methodology Deployment Guide

## Overview

This document describes how to set up and verify the Tsushin development methodology enforcement system: slash commands, hooks, and symlinks.

## Prerequisites

- Claude Code CLI installed
- Repository cloned at `/Users/vinicios/code/tsushin`
- Docker Desktop running
- Playwright MCP configured

## Setup Steps

### 1. Verify Directory Structure

```
methodology/
  METHODOLOGY.md          # This lifecycle document
  DEPLOY.md               # This setup guide
  commands/
    fire_regression.md     # Targeted regression command
    fire_remediation.md    # Bug tracking processor
    fire_full_regression.md # Full platform audit
  hooks/
    e2e-test-gate.sh       # Stop gate: regression before done
    commit-test-gate.sh    # Commit gate: blocks untested commits
    regression-test-gate.sh # Restart gate: demands testing after service restart
```

### 2. Verify Symlinks

The `.claude/commands` and `.claude/hooks` directories should be symlinks pointing to the methodology folder:

```bash
cd /Users/vinicios/code/tsushin

# Check symlinks exist and point correctly
ls -la .claude/commands
# Expected: commands -> ../methodology/commands

ls -la .claude/hooks
# Expected: hooks -> ../methodology/hooks
```

If missing, create them:

```bash
cd /Users/vinicios/code/tsushin/.claude
ln -sf ../methodology/commands commands
ln -sf ../methodology/hooks hooks
```

### 3. Make Hooks Executable

```bash
chmod +x /Users/vinicios/code/tsushin/methodology/hooks/*.sh
```

### 4. Verify settings.json

Check that `/Users/vinicios/code/tsushin/.claude/settings.json` contains the hook configurations:

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "/Users/vinicios/code/tsushin/methodology/hooks/e2e-test-gate.sh"
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "/Users/vinicios/code/tsushin/methodology/hooks/commit-test-gate.sh \"$TOOL_INPUT\""
          }
        ],
        "description": "Blocks git commit without regression confirmation"
      },
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "/Users/vinicios/code/tsushin/methodology/hooks/regression-test-gate.sh \"$TOOL_INPUT\""
          }
        ],
        "description": "Demands testing after docker restart"
      }
    ]
  }
}
```

### 5. Quick Validation

Run these checks to confirm everything is wired up:

```bash
# 1. Symlinks resolve
ls /Users/vinicios/code/tsushin/.claude/commands/fire_regression.md
ls /Users/vinicios/code/tsushin/.claude/hooks/e2e-test-gate.sh

# 2. Hooks are executable
test -x /Users/vinicios/code/tsushin/methodology/hooks/e2e-test-gate.sh && echo "OK"
test -x /Users/vinicios/code/tsushin/methodology/hooks/commit-test-gate.sh && echo "OK"
test -x /Users/vinicios/code/tsushin/methodology/hooks/regression-test-gate.sh && echo "OK"

# 3. Commands are accessible (list them)
ls -la /Users/vinicios/code/tsushin/.claude/commands/

# 4. BUGS.md exists
test -f /Users/vinicios/code/tsushin/BUGS.md && echo "BUGS.md OK"
```

### 6. Verify .gitignore

Ensure `BUGS.md` is gitignored (it is a working document, not committed):

```bash
grep "BUGS.md" /Users/vinicios/code/tsushin/.gitignore
```

The `methodology/` directory itself IS tracked in git -- it is project infrastructure.

## Troubleshooting

### Hooks not firing

- Verify `.claude/settings.json` exists and has the hooks configuration
- Verify the hook scripts are executable (`chmod +x`)
- Verify the symlinks are not broken (`ls -la .claude/hooks/`)

### Commands not found

- Verify `.claude/commands` symlink resolves: `ls .claude/commands/`
- If broken: `cd .claude && rm -f commands && ln -sf ../methodology/commands commands`

### BUGS.md missing

- Create it manually:
  ```bash
  cat > /Users/vinicios/code/tsushin/BUGS.md << 'EOF'
  # Tsushin Bug Tracker
  **Open:** 0 | **In Progress:** 0 | **Resolved:** 0
  ## Open Issues
  (none)
  ## Closed Issues
  (none)
  EOF
  ```

## How It Works

### Development Flow

1. Developer starts a task (feature, fix, refactor)
2. Follows the 6-phase lifecycle in METHODOLOGY.md
3. During Phase 6 (Validate), runs `/fire_regression` to test
4. `/fire_regression` auto-triggers `/fire_remediation` to update BUGS.md
5. When developer says "done" or stops, the **e2e-test-gate** checks for evidence of regression testing
6. When developer tries to `git commit`, the **commit-test-gate** checks for regression confirmation
7. When Docker services are restarted, the **regression-test-gate** demands re-testing

### Hook Enforcement Model

The hooks use a **soft enforcement** model -- they warn and request confirmation rather than hard-blocking. This prevents frustrating developers while still ensuring awareness:

- **Stop gate:** Reminds to run regression if no evidence found in conversation
- **Commit gate:** Asks for confirmation that testing was done before allowing commit
- **Regression gate:** Flags that services were restarted and testing may be needed
