#!/usr/bin/env bash
set -euo pipefail

VPS_HOST="184.174.34.245"
VPS_USER="root"
VPS_PASS="cb1312ef"
VPS_DIR="/opt/nexuslayer/graphvault"
NGINX_AVAILABLE="/etc/nginx/sites-available/graph.nexuslayer.eu"
NGINX_ENABLED="/etc/nginx/sites-enabled/graph.nexuslayer.eu"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"

SSH="sshpass -p ${VPS_PASS} ssh -o StrictHostKeyChecking=no ${VPS_USER}@${VPS_HOST}"
SCP="sshpass -p ${VPS_PASS} scp -o StrictHostKeyChecking=no"

echo "==> Creating remote directory ${VPS_DIR}"
${SSH} "mkdir -p ${VPS_DIR}"

echo "==> Syncing graphvault/ to VPS"
sshpass -p "${VPS_PASS}" rsync -avz --progress \
    --exclude 'node_modules' \
    --exclude '__pycache__' \
    --exclude '.git' \
    --exclude 'dist' \
    -e "ssh -o StrictHostKeyChecking=no" \
    "${LOCAL_DIR}/" \
    "${VPS_USER}@${VPS_HOST}:${VPS_DIR}/"

echo "==> Copying nginx config"
${SCP} "${LOCAL_DIR}/nginx-graphvault.conf" \
    "${VPS_USER}@${VPS_HOST}:${NGINX_AVAILABLE}"

echo "==> Creating nginx symlink (if not exists)"
${SSH} "[ -L ${NGINX_ENABLED} ] || ln -s ${NGINX_AVAILABLE} ${NGINX_ENABLED}"

echo "==> Building and starting containers"
${SSH} "cd ${VPS_DIR} && docker compose up --build -d"

echo "==> Waiting 5 seconds for containers to settle"
sleep 5

echo "==> Testing nginx config and reloading"
${SSH} "nginx -t && systemctl reload nginx"

echo "==> Checking SSL certificate"
${SSH} "
if [ ! -f /etc/letsencrypt/live/graph.nexuslayer.eu/fullchain.pem ]; then
    echo 'No cert found — running certbot'
    certbot --nginx -d graph.nexuslayer.eu --non-interactive --agree-tos -m admin@nexuslayer.eu
else
    echo 'SSL cert already exists — skipping certbot'
fi
"

echo ""
echo "GraphVault deployed at https://graph.nexuslayer.eu"
