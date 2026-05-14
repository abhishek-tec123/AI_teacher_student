# Setup Guide

Quick setup for running this project on any system.

## Prerequisites

- Python 3.10 or higher
- Make (usually pre-installed on macOS/Linux)

## Quick Start (One Command)

```bash
make setup
```

This will:
1. Install `uv` (fast Python package manager)
2. Create virtual environment (`.venv`)
3. Install all dependencies from `requirements.txt`

## Running the Server

```bash
make run
```

Server starts at: http://localhost:8000

API docs available at: http://localhost:8000/docs

## Available Commands

| Command | Description |
|---------|-------------|
| `make setup` | Full setup (install uv + venv + deps) |
| `make install` | Update dependencies |
| `make run` | Start development server with reload |
| `make run-prod` | Start production server (4 workers) |
| `make clean` | Remove venv and cache files |
| `make help` | Show all commands |

## Manual Setup (Without Make)

If you prefer not to use Make:

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create venv and install deps
uv venv
uv pip install -r requirements.txt

# Run server
uv run uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

## Environment Variables

Create a `.env` file in the project root:

```env
MONGODB_URI=mongodb://localhost:27017/teacher_ai
GROQ_API_KEY=your_groq_api_key_here
```

## Verify Installation

```bash
# Check server is running
curl http://localhost:8000/api/v1/core/health

# Expected: {"status": "healthy"}
```

## Troubleshooting

**Issue:** `uv: command not found`  
**Fix:** Run `export PATH="$HOME/.cargo/bin:$PATH"` or restart terminal

**Issue:** `ModuleNotFoundError`  
**Fix:** Run `make install` to ensure dependencies are installed

**Issue:** Port 8000 already in use  
**Fix:** Change port in Makefile or run `lsof -ti:8000 | xargs kill`
