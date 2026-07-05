#!/usr/bin/env bash
# ================================================
# AuraFlow VPS Setup Script
# Run as root on a fresh Ubuntu 22.04/24.04 Hetzner VPS
# Usage: bash setup-vps.sh
# ================================================
set -euo pipefail

echo "=== AuraFlow VPS Setup ==="

# -- 1. System updates --------------------------
echo "[1/8] Updating system..."
apt-get update && apt-get upgrade -y
apt-get install -y curl wget git ufw software-properties-common

# -- 2. Install Docker --------------------------
echo "[2/8] Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
else
    echo "Docker already installed."
fi

# Verify docker compose plugin
docker compose version

# -- 3. Install Nginx ---------------------------
echo "[3/8] Installing Nginx..."
apt-get install -y nginx
systemctl enable nginx

# -- 4. Install Certbot -------------------------
echo "[4/8] Installing Certbot..."
apt-get install -y certbot python3-certbot-nginx

# -- 5. Create deploy user ----------------------
echo "[5/8] Setting up deploy user..."
if ! id "deploy" &>/dev/null; then
    useradd -m -s /bin/bash deploy
    echo "Created 'deploy' user."
else
    echo "'deploy' user already exists."
fi

usermod -aG docker deploy

# Set up SSH for deploy user if not already done
mkdir -p /home/deploy/.ssh
if [ ! -f /home/deploy/.ssh/authorized_keys ]; then
    touch /home/deploy/.ssh/authorized_keys
    echo "Add your deploy public key to /home/deploy/.ssh/authorized_keys"
fi
chmod 700 /home/deploy/.ssh
chmod 600 /home/deploy/.ssh/authorized_keys
chown -R deploy:deploy /home/deploy/.ssh

# -- 6. Create app directory --------------------
echo "[6/8] Setting up /opt/auraflow..."
mkdir -p /opt/auraflow/infra/docker/postgres
mkdir -p /opt/auraflow/infra/nginx
mkdir -p /opt/auraflow/infra/scripts
chown -R deploy:deploy /opt/auraflow

# -- 7. Firewall --------------------------------
echo "[7/8] Configuring firewall..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP (certbot + redirect)
ufw allow 443/tcp   # HTTPS
ufw --force enable
echo "Firewall enabled: SSH(22), HTTP(80), HTTPS(443) open."

# -- 8. Login to GHCR ---------------------------
echo "[8/8] GHCR login..."
echo ""
echo "The deploy user needs to pull images from GHCR."
echo "Run the following as the deploy user:"
echo ""
echo "  su - deploy"
echo "  echo 'YOUR_GITHUB_PAT' | docker login ghcr.io -u KinovaAI --password-stdin"
echo ""

# -- Summary ------------------------------------
echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo ""
echo "  1. Copy project files to VPS:"
echo "     scp docker-compose.prod.yml deploy@YOUR_VPS:/opt/auraflow/"
echo "     scp .env.prod deploy@YOUR_VPS:/opt/auraflow/"
echo "     scp -r infra/ deploy@YOUR_VPS:/opt/auraflow/"
echo ""
echo "  2. Copy nginx config:"
echo "     sudo cp /opt/auraflow/infra/nginx/nginx.prod.conf /etc/nginx/nginx.conf"
echo ""
echo "  3. Point DNS for auraflow.fit, app.auraflow.fit, api.auraflow.fit to this server"
echo ""
echo "  4. Get SSL certs (after DNS propagates):"
echo "     sudo certbot --nginx -d auraflow.fit -d www.auraflow.fit -d app.auraflow.fit -d api.auraflow.fit"
echo ""
echo "  5. Login to GHCR as deploy user:"
echo "     su - deploy"
echo "     echo 'GITHUB_PAT' | docker login ghcr.io -u KinovaAI --password-stdin"
echo ""
echo "  6. Start services:"
echo "     cd /opt/auraflow && docker compose -f docker-compose.prod.yml pull && docker compose -f docker-compose.prod.yml up -d"
echo ""
echo "  7. Verify:"
echo "     curl -f http://localhost:8000/health"
echo "     curl -f http://localhost:3000/"
echo ""
