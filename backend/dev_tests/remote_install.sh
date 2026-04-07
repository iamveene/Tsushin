#!/bin/bash
###############################################################################
# Tsushin Remote Installation Script
# Phase 0: Safety Infrastructure
#
# Deploys Tsushin to a remote Ubuntu VM via SSH
#
# Usage:
#   ./remote_install.sh <user@host> [remote_path]
#
# Example:
#   ./remote_install.sh parallels@192.168.1.100
#   ./remote_install.sh root@ubuntu-vm.local /opt/tsushin
###############################################################################

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# SSH options (allow interactive password auth; accept new host keys automatically)
SSH_OPTS=(-o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new)

# Parse arguments
if [ -z "$1" ]; then
    echo -e "${RED}Error: Remote host required${NC}"
    echo "Usage: $0 <user@host> [remote_path]"
    echo "Example: $0 parallels@192.168.1.100"
    exit 1
fi

REMOTE_HOST="$1"

echo -e "${BLUE}"
echo "╔════════════════════════════════════════════════════════════╗"
echo "║         Tsushin Remote Installation Script                ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo -e "Remote Host: ${GREEN}$REMOTE_HOST${NC}"
echo -e "${YELLOW}Note:${NC} SSH password prompts are expected when using password-based VM access."
echo ""

###############################################################################
# Step 1: Check SSH Connectivity
###############################################################################
echo -e "${YELLOW}[1/5] Checking SSH connection...${NC}"
if ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" "printf 'Connected'" &>/dev/null; then
    echo -e "${GREEN}✓${NC} SSH connection successful"
else
    echo -e "${RED}✗${NC} SSH connection failed"
    echo ""
    echo "Troubleshooting:"
    echo "  1. Check if SSH server is running on remote host"
    echo "  2. Verify the hostname/IP is correct"
    echo "  3. Ensure SSH key is added or password authentication is enabled"
    echo "  4. Try: ssh $REMOTE_HOST"
    exit 1
fi

if [ "${2:-}" != "" ]; then
    REMOTE_PATH="$2"
else
    REMOTE_HOME="$(ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" 'printf %s "$HOME"')"
    REMOTE_PATH="${REMOTE_HOME}/tsushin"
fi

echo -e "Remote Path: ${GREEN}$REMOTE_PATH${NC}"
echo ""

###############################################################################
# Step 2: Install Prerequisites on Ubuntu VM
###############################################################################
echo -e "${YELLOW}[2/5] Installing prerequisites on remote host...${NC}"
ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" bash << 'ENDSSH'
    set -e

    echo "Updating package list..."
    sudo apt-get update -qq

    # Install Docker
    if ! command -v docker &> /dev/null; then
        echo "Installing Docker..."
        sudo apt-get install -y -qq apt-transport-https ca-certificates curl software-properties-common gnupg

        # Add Docker's official GPG key
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

        # Add Docker repository
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

        # Install Docker
        sudo apt-get update -qq
        sudo apt-get install -y -qq docker-ce docker-ce-cli containerd.io

        # Add current user to docker group
        sudo usermod -aG docker $USER

        echo "✓ Docker installed successfully"
    else
        echo "✓ Docker already installed"
    fi

    # Install Docker Compose v2 plugin
    if ! docker compose version &> /dev/null; then
        echo "Installing Docker Compose v2..."
        sudo apt-get install -y -qq docker-compose-plugin || sudo apt-get install -y -qq docker-compose-v2
        echo "✓ Docker Compose v2 installed successfully"
    else
        echo "✓ Docker Compose v2 already installed"
    fi

    # Install Python 3 and pip
    if ! command -v python3 &> /dev/null; then
        echo "Installing Python 3..."
        sudo apt-get install -y -qq python3 python3-pip python3-venv rsync
        echo "✓ Python 3 installed successfully"
    else
        echo "✓ Python 3 already installed"
        if ! command -v rsync &> /dev/null; then
            echo "Installing rsync..."
            sudo apt-get install -y -qq rsync
            echo "✓ rsync installed successfully"
        else
            echo "✓ rsync already installed"
        fi
    fi

    # Install required Python packages
    echo "Installing Python packages..."
    python3 -m pip install --quiet --user python-dotenv requests cryptography || \
        python3 -m pip install --quiet --user --break-system-packages python-dotenv requests cryptography

    # Verify installations
    echo ""
    echo "Installed versions:"
    echo "  - Docker: $(docker --version | awk '{print $3}' | sed 's/,$//')"
    echo "  - Docker Compose: $(docker compose version --short 2>/dev/null || docker compose version | head -n1)"
    echo "  - Python: $(python3 --version | awk '{print $2}')"
    echo ""
    echo "✓ All prerequisites installed"
ENDSSH

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Prerequisites installed successfully"
else
    echo -e "${RED}✗${NC} Failed to install prerequisites"
    exit 1
fi
echo ""

###############################################################################
# Step 3: Copy Tsushin Codebase to Remote
###############################################################################
echo -e "${YELLOW}[3/5] Copying codebase to remote host...${NC}"
echo "This may take a few minutes depending on your network speed..."

# Create remote directory
ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" "mkdir -p '$REMOTE_PATH'"

# Use rsync to copy files (excludes unnecessary directories)
if command -v rsync &> /dev/null; then
    rsync -avz --progress \
        --exclude='backend/data' \
        --exclude='node_modules' \
        --exclude='.git' \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='.next' \
        --exclude='backups' \
        --exclude='logs' \
        --exclude='.env' \
        ./ "$REMOTE_HOST:$REMOTE_PATH/"

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓${NC} Codebase copied successfully"
    else
        echo -e "${RED}✗${NC} Failed to copy codebase"
        exit 1
    fi
else
    echo -e "${YELLOW}⚠${NC}  rsync not found, using scp (slower)..."
    scp -r ./* "$REMOTE_HOST:$REMOTE_PATH/"

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓${NC} Codebase copied successfully"
    else
        echo -e "${RED}✗${NC} Failed to copy codebase"
        exit 1
    fi
fi
echo ""

###############################################################################
# Step 4: Make Scripts Executable
###############################################################################
echo -e "${YELLOW}[4/5] Setting permissions...${NC}"
ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" bash << ENDSSH
    cd $REMOTE_PATH
    [ -f backup_installer.py ] && chmod +x backup_installer.py
    [ -f backend/dev_tests/remote_install.sh ] && chmod +x backend/dev_tests/remote_install.sh
    [ -f install.py ] && chmod +x install.py
    echo "✓ Permissions set"
ENDSSH
echo -e "${GREEN}✓${NC} Permissions configured"
echo ""

###############################################################################
# Step 5: Display Next Steps
###############################################################################
echo -e "${GREEN}"
echo "╔════════════════════════════════════════════════════════════╗"
echo "║           Installation Preparation Complete                ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo "Next steps:"
echo ""
echo "1. SSH into the remote host:"
echo -e "   ${BLUE}ssh $REMOTE_HOST${NC}"
echo ""
echo "2. Navigate to the installation directory:"
echo -e "   ${BLUE}cd $REMOTE_PATH${NC}"
echo ""
echo "3. Run the installer:"
echo -e "   ${BLUE}python3 install.py${NC}"
echo ""
echo -e "${YELLOW}IMPORTANT:${NC} When the installer asks about access type, choose 'remote'"
echo "            and provide the IP/hostname you'll use to access the system."
echo -e "            Example: ${GREEN}${REMOTE_HOST##*@}${NC}"
echo ""
echo "4. After installation, access Tsushin at:"
echo -e "   ${BLUE}http://${REMOTE_HOST##*@}:3030${NC}"
echo ""
echo "Alternative: Run installer automatically (experimental):"
echo -e "   ${BLUE}ssh -t $REMOTE_HOST 'cd $REMOTE_PATH && python3 install.py'${NC}"
echo ""
echo -e "${YELLOW}Note:${NC} For Docker permissions, you may need to log out and back in,"
echo "      or use 'sudo' with docker commands on first run."
echo ""

# Optional: Ask if user wants to run installer now
read -p "Would you like to SSH to the remote host now? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${BLUE}Connecting to $REMOTE_HOST...${NC}"
    ssh -t "$REMOTE_HOST" "cd $REMOTE_PATH && exec bash"
fi
