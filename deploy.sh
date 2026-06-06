#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# Deploy AITrading to server
# Usage: ./deploy.sh [server-ip]
#
# What it does:
#   1. Pushes latest code to GitHub
#   2. SSHes into the server
#   3. Pulls latest code + rebuilds containers
#   4. Shows container status
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SERVER_USER="ubuntu"
SERVER_IP="${1:-YOUR_SERVER_IP}"     # pass IP as argument or edit this
SSH_KEY="~/.ssh/oracle_trading"      # path to your SSH key
REMOTE_DIR="~/asx-ai-trading"
COMPOSE_FILE="docker-compose.server.yml"

if [[ "$SERVER_IP" == "YOUR_SERVER_IP" ]]; then
    echo "Usage: ./deploy.sh <server-ip>"
    echo "   or: edit SERVER_IP in this script"
    exit 1
fi

SSH_CMD="ssh -i $SSH_KEY $SERVER_USER@$SERVER_IP"

echo "=== Step 1: Push to GitHub ==="
git push origin master 2>/dev/null || git push origin main

echo ""
echo "=== Step 2: Pull + Rebuild on server ==="
$SSH_CMD "cd $REMOTE_DIR && git pull && docker compose -f $COMPOSE_FILE up -d --build"

echo ""
echo "=== Step 3: Container Status ==="
$SSH_CMD "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"

echo ""
echo "=== Step 4: IB Gateway Health ==="
$SSH_CMD "sleep 5 && docker compose -f $REMOTE_DIR/$COMPOSE_FILE logs ib-gateway --tail 10"

echo ""
echo "Done. Tail logs with:"
echo "  $SSH_CMD \"docker compose -f $REMOTE_DIR/$COMPOSE_FILE logs -f asx_scheduler\""
