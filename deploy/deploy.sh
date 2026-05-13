#!/usr/bin/env bash
set -euo pipefail

# AI Teacher — Production Deploy Script
# Pushes feat/in-progress code to AWS EC2 and restarts the service.

SERVER_USER="ubuntu"
SERVER_HOST="ec2-13-233-214-195.ap-south-1.compute.amazonaws.com"
SERVER_DIR="/home/ubuntu/AI_Teacher"
SERVICE_NAME="AITEACHER"

# SSH key path: pass as first argument, or set KEY env var, or use default
KEY="${1:-${KEY:-/Users/macbook/Desktop/server/tecorb_server_r6g_large.pem}}"

echo "==> Starting deployment to $SERVER_HOST"

# Ensure we're in the repo root
if [ ! -f "src/main.py" ]; then
    echo "Error: must run deploy.sh from repo root (where src/main.py exists)"
    exit 1
fi

# Sync code to server (exclude local env, venv, storage, git)
echo "==> Syncing code to server..."
rsync -avz --delete \
    --exclude='.git' \
    --exclude='.venv' \
    --exclude='.env' \
    --exclude='storage' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.DS_Store' \
    --exclude='.pytest_cache' \
    --exclude='.coverage' \
    --exclude='htmlcov' \
    --exclude='*.log' \
    ./ "$SERVER_USER@$SERVER_HOST:$SERVER_DIR/"

# SSH commands to install deps, update systemd, restart service
echo "==> Installing dependencies and restarting service..."
ssh -i "$KEY" "$SERVER_USER@$SERVER_HOST" bash -s << 'REMOTE_SCRIPT'
set -euo pipefail
SERVER_DIR="/home/ubuntu/AI_Teacher"
SERVICE_NAME="AITEACHER"

cd "$SERVER_DIR"

# Ensure uv is installed
if ! command -v uv &> /dev/null; then
    echo "==> uv not found, installing..."
    curl -LsSf https://astral.sh/uv/0.5.0/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
fi

# Ensure virtualenv exists, then install dependencies with uv
if [ ! -d ".venv" ]; then
    echo "==> Creating .venv..."
    uv venv
fi

echo "==> Installing dependencies into .venv..."
uv pip install -r requirements.txt

# Copy updated systemd service
sudo cp "$SERVER_DIR/deploy/AITEACHER.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

# Wait a moment for startup
sleep 3

# Verify health
echo "==> Checking health endpoint..."
curl -sf http://127.0.0.1:3018/api/v1/core/health || {
    echo "Health check failed. Check logs: sudo journalctl -u $SERVICE_NAME -n 50"
    exit 1
}

echo "==> Deployment complete. Service is healthy."
REMOTE_SCRIPT

echo "==> Done. Test externally: curl https://api.tecorb.in/api/v1/core/health"
