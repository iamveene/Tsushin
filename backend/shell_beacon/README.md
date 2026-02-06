# Tsushin Shell Beacon

A lightweight Python beacon client for remote command execution. Part of the Shell Skill C2 architecture.

## Overview

The Shell Beacon connects to a Tsushin backend server and executes shell commands on the host machine. It implements a polling-based C2 (Command & Control) architecture:

1. **Register** - Beacon registers with the server on startup
2. **Poll** - Beacon periodically checks for pending commands
3. **Execute** - Commands are executed locally with stacked execution support
4. **Report** - Results are reported back to the server

## Features

- 🔄 **HTTP Polling** - Reliable polling-based command retrieval
- 📦 **Stacked Execution** - Execute multiple commands in sequence with `cd` tracking
- 🔐 **Secure API Keys** - SHA-256 hashed API key authentication
- 📁 **Configuration** - YAML config file, environment variables, or CLI arguments
- 📝 **Logging** - File logging with rotation
- 🔄 **Auto-Update** - Self-update capability from server
- 🛑 **Graceful Shutdown** - Proper signal handling (SIGTERM, SIGINT)
- 🔁 **Exponential Backoff** - Smart reconnection on failures

## Installation

### From Package

```bash
# Download from Tsushin server
curl -o tsushin_beacon.zip https://your-server.com/api/shell/beacon/download
unzip tsushin_beacon.zip
cd shell_beacon
pip install -r requirements.txt
```

### Manual

```bash
# Clone the repository
git clone https://github.com/your-org/tsushin.git
cd tsushin/backend/shell_beacon
pip install -r requirements.txt
```

## Configuration

### 1. Create Configuration File

```bash
mkdir -p ~/.tsushin
cat > ~/.tsushin/beacon.yaml << 'EOF'
server:
  url: "https://your-tsushin-server.com/api/shell"
  api_key: "shb_your_api_key_here"

connection:
  poll_interval: 5
  reconnect_delay: 5
  max_reconnect_delay: 300
  request_timeout: 30

execution:
  shell: "/bin/bash"
  timeout: 300
  working_dir: ""

logging:
  level: "INFO"
  file: "~/.tsushin/beacon.log"
  max_size_mb: 10
  backup_count: 5

update:
  enabled: true
  check_on_startup: true
  check_interval_hours: 24
EOF
```

### 2. Get API Key

Create a Shell Integration in the Tsushin UI or via API:

```bash
curl -X POST "https://your-server.com/api/shell/integrations" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "my-server", "poll_interval": 5}'
```

Save the returned API key - it cannot be retrieved later!

## Usage

### Quick Start (Recommended)

After downloading and extracting the beacon, run the wrapper script directly:

```bash
# From the shell_beacon directory
cd shell_beacon
python run.py \
  --server https://your-server.com/api/shell \
  --api-key shb_your_key_here
```

### Run as Module (Alternative)

**IMPORTANT**: When using `python -m shell_beacon`, you must run from the **parent** directory containing the `shell_beacon/` folder, NOT from inside it:

```bash
# Download and extract to /tmp
curl -L "https://your-server.com/api/shell/beacon/download" -o beacon.zip
unzip beacon.zip

# CORRECT: Run from parent directory (/tmp in this case)
cd /tmp                         # Parent directory containing shell_beacon/
python -m shell_beacon \
  --server https://your-server.com/api/shell \
  --api-key shb_your_key_here

# WRONG: This will NOT work!
cd /tmp/shell_beacon           # Inside the package
python -m shell_beacon         # ❌ "No module" error
```

### Run with Config File

```bash
# Create config file first (see Configuration section)
cd /path/to/parent              # Parent of shell_beacon/
python -m shell_beacon
# or from inside shell_beacon/
python run.py
```

### Run with CLI Arguments

```bash
# Using module (from parent directory)
python -m shell_beacon \
  --server https://your-server.com/api/shell \
  --api-key shb_your_key_here \
  --poll-interval 5

# Using wrapper script (from inside shell_beacon/)
python run.py \
  --server https://your-server.com/api/shell \
  --api-key shb_your_key_here \
  --poll-interval 5
```

### Run with Environment Variables

```bash
export TSUSHIN_SERVER_URL="https://your-server.com/api/shell"
export TSUSHIN_API_KEY="shb_your_key_here"

# From parent directory
python -m shell_beacon

# Or from inside shell_beacon/
python run.py
```

### Configuration Priority

1. CLI arguments (highest)
2. Environment variables
3. Config file
4. Default values (lowest)

## CLI Options

```
usage: tsushin-beacon [-h] [-s URL] [-k KEY] [-p SECONDS] [--shell PATH]
                      [--timeout SECONDS] [--working-dir PATH]
                      [--log-level {DEBUG,INFO,WARNING,ERROR}]
                      [--log-file PATH] [-c FILE] [--no-auto-update]
                      [-v] [--dump-config]

Tsushin Shell Beacon - Remote Command Execution Agent

Server Options:
  -s, --server URL      Tsushin server URL
  -k, --api-key KEY     Beacon API key (starts with 'shb_')

Connection Options:
  -p, --poll-interval   Polling interval in seconds (default: 5)

Execution Options:
  --shell PATH          Shell to use (default: /bin/bash)
  --timeout SECONDS     Command timeout in seconds (default: 300)
  --working-dir PATH    Initial working directory

Logging Options:
  --log-level LEVEL     Logging level (default: INFO)
  --log-file PATH       Log file path (default: ~/.tsushin/beacon.log)

Other Options:
  -c, --config FILE     Configuration file path
  --no-auto-update      Disable automatic updates
  -v, --version         Show version and exit
  --dump-config         Dump effective configuration and exit
```

## Running as a Service

### Systemd (Linux)

Create `/etc/systemd/system/tsushin-beacon.service`:

```ini
[Unit]
Description=Tsushin Shell Beacon
After=network.target

[Service]
Type=simple
User=tsushin
Group=tsushin
WorkingDirectory=/opt/tsushin-beacon
ExecStart=/usr/bin/python3 -m shell_beacon
Restart=always
RestartSec=10
Environment="TSUSHIN_API_KEY=shb_your_key_here"
Environment="TSUSHIN_SERVER_URL=https://your-server.com/api/shell"

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable tsushin-beacon
sudo systemctl start tsushin-beacon
sudo systemctl status tsushin-beacon
```

### macOS (launchd)

Create `~/Library/LaunchAgents/com.tsushin.beacon.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.tsushin.beacon</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>-m</string>
        <string>shell_beacon</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/opt/tsushin-beacon</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/var/log/tsushin-beacon.log</string>
    <key>StandardErrorPath</key>
    <string>/var/log/tsushin-beacon.err</string>
</dict>
</plist>
```

Load and start:

```bash
launchctl load ~/Library/LaunchAgents/com.tsushin.beacon.plist
launchctl start com.tsushin.beacon
```

## Command Execution

The beacon supports stacked command execution with working directory tracking:

```json
{
  "commands": [
    "cd /var/log",
    "ls -la",
    "grep error syslog | tail -20",
    "cd /tmp",
    "pwd"
  ]
}
```

- `cd` commands update the working directory for subsequent commands
- Commands run sequentially (stop on first failure by default)
- Full stdout/stderr captured for each command
- Execution time tracked per command

## Security Considerations

1. **API Key Protection**: Store API keys securely (environment variables, secret managers)
2. **TLS/HTTPS**: Always use HTTPS in production
3. **Command Whitelisting**: Configure `allowed_commands` on the integration
4. **Path Restrictions**: Configure `allowed_paths` to limit accessible directories
5. **Minimal Permissions**: Run beacon with minimal required permissions

## Troubleshooting

### Check Logs

```bash
tail -f ~/.tsushin/beacon.log
```

### Verify Configuration

```bash
python -m shell_beacon --dump-config
```

### Test Connection

```bash
curl -H "X-API-Key: shb_your_key" \
  https://your-server.com/api/shell/register \
  -d '{"hostname": "test", "os_info": {}}'
```

### Common Issues

| Issue | Solution |
|-------|----------|
| "Invalid API key" | Verify API key, regenerate if needed |
| Connection refused | Check server URL and firewall |
| Commands not executing | Check beacon is registered and polling |
| Timeout errors | Increase `request_timeout` or `execution.timeout` |

## Development

### Run Tests

```bash
cd backend
pytest tests/test_shell_beacon.py -v
```

### Local Development

```bash
# Start local Tsushin backend
docker-compose up -d backend

# Run beacon with debug logging
python -m shell_beacon \
  --server http://localhost:8000/api/shell \
  --api-key shb_test_key \
  --log-level DEBUG
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Tsushin Backend                          │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐  │
│  │  Shell Routes   │  │  ShellCommand   │  │   Database  │  │
│  │  (API Layer)    │──│  (Queue)        │──│  (SQLite)   │  │
│  └─────────────────┘  └─────────────────┘  └─────────────┘  │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP/HTTPS
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                     Shell Beacon                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   Beacon    │──│   Executor  │──│  Shell (bash/cmd)   │  │
│  │  (Polling)  │  │  (Commands) │  │  (Local Execution)  │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   Config    │  │   Updater   │  │      Logger         │  │
│  │  (YAML/CLI) │  │  (Updates)  │  │  (File Rotation)    │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## License

Part of the Tsushin project. See main repository for license information.

## Version History

- **1.0.0** - Initial release
  - HTTP polling mode
  - Stacked command execution with `cd` tracking
  - File logging with rotation
  - Auto-update capability
  - YAML/CLI/ENV configuration
