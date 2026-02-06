#!/bin/bash
# Sync MCP databases from container volumes to backend-accessible locations
# This runs in the background to keep databases in sync for the watcher

# Use environment variables for paths (with defaults for local dev)
BACKEND_DATA="${BACKEND_DATA_PATH:-./backend/data}"
MCP_STORE="${MCP_STORE_PATH:-./backend/whatsapp-mcp/store}"
TENANT_ID="${TENANT_ID:-default_tenant}"
MCP_INSTANCE_ID="${MCP_INSTANCE_ID:-default_instance}"

while true; do
    # Sync agent MCP database
    if [ -f "$MCP_STORE/messages.db" ]; then
        TARGET="$BACKEND_DATA/mcp/$TENANT_ID/$MCP_INSTANCE_ID"
        mkdir -p "$TARGET"
        cp "$MCP_STORE/messages.db" "$TARGET/messages.db" 2>/dev/null
    fi

    sleep 1
done
