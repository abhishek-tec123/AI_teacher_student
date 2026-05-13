.PHONY: help setup install run dev check-uv train-dpo clean run-server

# Python and project settings
PYTHON := python3
VENV_DIR := .venv
UV_VERSION := 0.5.0

# Default target
help:
	@echo "Available commands:"
	@echo "  make setup      - Full setup: install uv, create venv, install deps"
	@echo "  make install    - Install/update dependencies"
	@echo "  make run        - Run the FastAPI server (with reload)"
	@echo "  make dev        - Run server in development mode (alias for run)"
	@echo "  make clean      - Remove venv and cached files"
	@echo "  make train-dpo  - Run the DPO training script"
	@echo "  make check-uv   - Check if uv is installed"

# Check if uv is installed
check-uv:
	@which uv > /dev/null 2>&1 || (echo "❌ uv not found. Installing uv..." && $(MAKE) install-uv)

# Install uv package manager
install-uv:
	@echo "📦 Installing uv..."
	@curl -LsSf https://astral.sh/uv/$(UV_VERSION)/install.sh | sh
	@echo "✅ uv installed. Please restart your terminal or run: export PATH="$$HOME/.cargo/bin:$$PATH""

# Full setup for new systems
setup: check-uv
	@echo "🚀 Setting up project environment..."
	@echo "📦 Creating virtual environment..."
	@uv venv
	@echo "📥 Installing dependencies..."
	@uv pip install -r requirements.txt
	@echo "✅ Setup complete! Run 'make run' to start the server."

# Install/update dependencies
install: check-uv
	@echo "📥 Installing/updating dependencies..."
	@uv pip install -r requirements.txt
	@echo "✅ Dependencies installed."

# Run the FastAPI server with auto-reload
dev: run

# Run the FastAPI server
run: check-uv
	@echo "🚀 Starting FastAPI server..."
	@uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Run the FastAPI server (production mode, no reload)
run-prod: check-uv
	@echo "🚀 Starting FastAPI server (production mode)..."
	@uv run uvicorn src.main:app --host 0.0.0.0 --port 3018 --workers 4

# Run with ngrok (for external access)
run-server:
	@ngrok http 8000

# Run the DPO training script
train-dpo: check-uv
	@uv run python src/student/services/dpo_trainer.py

# Clean up virtual environment and cache
clean:
	@echo "🧹 Cleaning up..."
	@rm -rf $(VENV_DIR)
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "✅ Cleanup complete."

# Quick start (setup + run)
start: setup run
