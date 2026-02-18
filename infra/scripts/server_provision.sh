#!/bin/bash
set -e

# Configuration
IB_USER="ibbot"
IB_UID=1001  # Adjust if needed, but distinct from root
DOCKER_COMPOSE_VERSION="v2.24.5" 

echo ">>> Starting Server Provisioning..."

# 1. Update System
echo ">>> Updating system packages..."
apt-get update && apt-get upgrade -y
apt-get install -y curl wget git vim ufw fail2ban xvfb x11vnc

# 2. Configure Firewall
echo ">>> Configuring Firewall..."
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 5900/tcp # VNC for initial setup (close this later!)
# Enable firewall non-interactively
echo "y" | ufw enable

# 3. Create Application User
if id "$IB_USER" &>/dev/null; then
    echo ">>> User $IB_USER already exists."
else
    echo ">>> Creating user $IB_USER..."
    adduser --disabled-password --gecos "" $IB_USER
    usermod -aG sudo $IB_USER
fi

# 4. Install Docker & Docker Compose
if ! command -v docker &> /dev/null; then
    echo ">>> Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    usermod -aG docker $IB_USER
    systemctl enable docker
    systemctl start docker
else
    echo ">>> Docker already installed."
fi

# 5. Install IB Gateway dependencies
echo ">>> Installing IB Gateway dependencies..."
# Libs often needed for IB Gateway GUI
apt-get install -y libxrender1 libxtst6 libxi6

# 6. Create Directory Structure
echo ">>> Setting up directory structure..."
mkdir -p /home/$IB_USER/ib_bot
mkdir -p /home/$IB_USER/backups
mkdir -p /home/$IB_USER/Jts
chown -R $IB_USER:$IB_USER /home/$IB_USER

echo ">>> Provisioning Complete!"
echo "Next steps:"
echo "1. Upload project files"
echo "2. Install IB Gateway"
echo "3. Configure .env"
