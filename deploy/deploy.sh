#!/usr/bin/env bash
set -euo pipefail

# AI Teacher — Production Deploy Script
# Works both from local Mac (rsync+ssh) and directly on the server (local deploy).

SERVER_USER="ubuntu"
SERVER_HOST="ec2-13-233-214-195.ap-south-1.compute.amazonaws.com"
SERVER_DIR="/home/ubuntu/AI_Teacher/AI_tescher_student"
SERVICE_NAME="AITEACHER"

# Detect if running on the server
# Method 1: hostname contains EC2 identifiers
# Method 2: current directory matches SERVER_DIR
IS_LOCAL_DEPLOY=false
HOSTNAME=$(hostname -f 2>/dev/null || hostname)
CURRENT_DIR=$(pwd -P)
if echo "$HOSTNAME" | grep -qE 'ip-172-31-43|ec2-13-233-214' || [ "$CURRENT_DIR" = "$SERVER_DIR" ]; then
    IS_LOCAL_DEPLOY=true
fi

# SSH key path: pass as first argument, or set KEY env var, or use default
KEY="${1:-${KEY:-/Users/macbook/Desktop/server/tecorb_server_r6g_large.pem}}"

echo "==> Starting deployment (local_deploy=$IS_LOCAL_DEPLOY)"

# Ensure we're in the repo root
if [ ! -f "src/main.py" ]; then
    echo "Error: must run deploy.sh from repo root (where src/main.py exists)"
    exit 1
fi

run_server_setup() {
    set -euo pipefail
    SERVER_DIR="/home/ubuntu/AI_Teacher/AI_tescher_student"
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
}

if [ "$IS_LOCAL_DEPLOY" = "true" ]; then
    echo "==> Running local deploy on server..."
    run_server_setup
    echo "==> Done. Test externally: curl https://api.tecorb.in/api/v1/core/health"
else
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

    echo "==> Installing dependencies and restarting service via SSH..."
    ssh -i "$KEY" "$SERVER_USER@$SERVER_HOST" "bash -s" < <(declare -f run_server_setup; echo "run_server_setup")

    echo "==> Done. Test externally: curl https://api.tecorb.in/api/v1/core/health"
fi
