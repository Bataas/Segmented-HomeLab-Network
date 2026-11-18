#!/usr/bin/env bash
# ==============================================================================
# Reproducible UniFi Network Server 10.6.109 Installation Script
# Target Environment: Debian 12 (Bookworm) Unprivileged LXC on Proxmox VE
# Container Specs: 2 vCPU, 2 GB RAM, 512 MB Swap, 16 GB Disk
# Network: vmbr0, VLAN tag 99, IP 192.168.99.4/24, GW/DNS 192.168.99.1
#
# Why this script exists:
# 1. Ubiquiti's legacy APT repo package index returns 0 bytes on amd64.
# 2. Debian 12 does not include MongoDB in default repositories.
# 3. UniFi Network Server 10.6.109 requires Java 25 (not Java 17/21), which is
#    provided via Eclipse Adoptium (temurin-25-jre).
# ==============================================================================

set -euo pipefail

echo "[1/5] Installing prerequisite packages..."
apt-get update
apt-get install -y curl gnupg apt-transport-https ca-certificates wget

echo "[2/5] Adding MongoDB 7.0 repository and installing mongodb-org-server..."
curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | \
    gpg --dearmor -o /usr/share/keyrings/mongodb-server-7.0.gpg
echo "deb [ signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] http://repo.mongodb.org/apt/debian bookworm/mongodb-org/7.0 main" \
    > /etc/apt/sources.list.d/mongodb-org-7.0.list
apt-get update
apt-get install -y mongodb-org-server

# Disable standalone mongod service because UniFi spawns its own instance on port 27117
systemctl disable --now mongod || true

echo "[3/5] Adding Eclipse Adoptium repository and installing Temurin 25 JRE..."
curl -fsSL https://packages.adoptium.net/artifactory/api/gpg/key/public | \
    gpg --dearmor -o /usr/share/keyrings/adoptium.gpg
echo "deb [ signed-by=/usr/share/keyrings/adoptium.gpg ] https://packages.adoptium.net/artifactory/deb bookworm main" \
    > /etc/apt/sources.list.d/adoptium.list
apt-get update
apt-get install -y temurin-25-jre

echo "[4/5] Downloading and installing UniFi Network Server .deb package..."
# Replace URL below with the direct Ubiquiti download link if updating
UNIFI_DEB="/tmp/unifi_sysvinit_all.deb"
if [ ! -f "$UNIFI_DEB" ]; then
    echo "Place the downloaded UniFi 10.6.109 .deb at $UNIFI_DEB and re-run."
    exit 1
fi
apt-get install -y "$UNIFI_DEB"

echo "[5/5] Verifying UniFi service..."
systemctl status unifi --no-pager
echo "UniFi Network Server is active at https://192.168.99.4:8443"
