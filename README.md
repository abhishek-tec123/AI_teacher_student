# Student Learning API

AI-powered adaptive learning backend built with FastAPI, LangChain, and MongoDB Atlas Vector Search.

## Overview

This backend powers an intelligent tutoring system with:
- **Student-facing chat** powered by Groq LLM with RAG vector search
- **Teacher-facing vector management** for curriculum documents
- **Admin dashboard** for global prompts, shared knowledge, and system settings
- **Multi-language support** (English, Hindi, Hinglish) with auto-detection
- **Text-to-speech** streaming via Edge TTS
- **Performance monitoring** and activity tracking

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        FastAPI App                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │  Auth    │  │ Student  │  │  Admin   │  │ Vectors  │    │
│  │ Routes   │  │ Routes   │  │ Routes   │  │ Routes   │    │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘    │
│       │             │             │             │            │
│  ┌────┴─────────────┴─────────────┴─────────────┴─────┐    │
│  │              Services & Agents Layer                │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐        │    │
│  │  │ Student  │  │ Teacher  │  │  Admin   │        │    │
│  │  │ Services │  │ Services │  │ Services │        │    │
│  │  └──────────┘  └──────────┘  └──────────┘        │    │
│  └───────────────────────────────────────────────────┘    │
│       │             │             │                      │
│  ┌────┴─────────────┴─────────────┴──────────────────┐    │
│  │              Data Layer                            │    │
│  │  MongoDB (Atlas)  │  Redis Cache  │  Vector Store   │    │
│  └───────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | FastAPI |
| LLM | Groq (Llama 4), Gemini |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) |
| Vector DB | MongoDB Atlas Vector Search |
| Cache | Redis |
| Auth | JWT (python-jose) + bcrypt |
| TTS | Edge TTS, gTTS, pyttsx3 |
| Document Processing | PyMuPDF, Pillow, pytesseract |
| ML | PyTorch, FAISS, spaCy |

## Project Structure

```
.
├── src/                          # Application source code
│   ├── main.py                   # FastAPI application entry point
│   ├── config/                   # Settings and logging configuration
│   ├── models/                   # Pydantic data models
│   ├── common/                   # Shared utilities, auth, middleware
│   │   ├── auth/                 # JWT, password utils, dependencies
│   │   ├── db/                   # Database and Redis connections
│   │   ├── middleware/           # Performance monitoring
│   │   ├── routes/               # Auth, activity, core, performance
│   │   ├── services/             # TTS, shared services
│   │   └── utils/              # Language detector, prompt templates
│   ├── student/                  # Student domain
│   │   ├── agents/               # Query handler, quiz generator, RL optimizer
│   │   ├── repositories/         # DB access for students, bookmarks, chats
│   │   ├── routes/               # Student API endpoints
│   │   ├── services/             # Business logic
│   │   └── utils/                # Agent utilities
│   ├── teacher/                  # Teacher domain
│   │   ├── embeddings/           # Text extraction, vector utilities
│   │   ├── repositories/         # Collections, search chunks
│   │   ├── routes/               # Vector management, search, topics
│   │   ├── search/               # Response cache, search utils
│   │   ├── services/             # Vector CRUD, similarity search, RAG
│   │   └── utils/                # Topic extraction
│   └── admin/                    # Admin domain
│       ├── repositories/         # Admin data access
│       ├── routes/               # Management, prompts, system
│       └── services/             # Global prompts, settings
├── scripts/                      # Utility scripts
│   ├── init_database.py          # DB initialization
│   ├── migrate_auth.py           # Auth migration helper
│   └── add_performance_to_existing.py
├── .env.example                  # Environment template
├── Makefile                      # Common commands
├── pyproject.toml                # Python dependencies
└── SETUP.md                      # Detailed setup guide
```

## Quick Start

### Prerequisites

- Python 3.11 or higher
- `make` (pre-installed on macOS/Linux)

### One-Command Setup

```bash
make setup
```

This installs `uv`, creates a virtual environment (`.venv`), and installs all dependencies.

### Run the Server

```bash
make run
```

Server starts at: http://localhost:8000

API docs: http://localhost:8000/docs

### Verify

```bash
curl http://localhost:8000/api/v1/core/health
# Expected: {"status": "healthy"}
```

## Environment Variables

Create a `.env` file from `.env.example`:

```bash
cp .env.example .env
```

Key variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `MONGODB_URI` | Yes | MongoDB Atlas connection string |
| `DB_NAME` | No | Database name (default: `tutor_ai`) |
| `JWT_SECRET_KEY` | Yes | Min 32 characters |
| `GROQ_API_KEY` | Yes | Groq API key for LLM |
| `GEMINI_API_KEY` | No | Gemini API key |
| `TAVILY_API_KEY` | No | Tavily search API key |
| `REDIS_HOST` | No | Redis host (default: `localhost`) |
| `REDIS_PORT` | No | Redis port (default: `6379`) |
| `CORS_ORIGINS` | No | Comma-separated allowed origins |

## Available Commands

| Command | Description |
|---------|-------------|
| `make setup` | Full setup (uv + venv + deps) |
| `make run` | Start development server with reload |
| `make run-prod` | Start production server (4 workers) |
| `make install` | Update dependencies |
| `make train-dpo` | Run DPO training script |
| `make clean` | Remove venv and cache files |
| `make help` | Show all commands |

## API Overview

The API is organized into 9 domains under `/api/v1/`:

| Domain | Prefix | Description |
|--------|--------|-------------|
| Auth | `/api/v1/auth` | Login, refresh tokens, password management |
| Student | `/api/v1/student` | Chat, bookmarks, sessions, documents, history |
| Admin | `/api/v1/admin` | Dashboard, prompts, shared knowledge, settings |
| Vectors | `/api/v1/vectors` | Vector search, agent CRUD, document management |
| Performance | `/api/v1/performance` | Agent metrics, health checks, analytics |
| Activity | `/api/v1/activity` | Recent activity, stats, activity types |
| Core | `/api/v1/core` | Health check |
| Topics | `/api/v1/topics` | Topic extraction from agents |
| TTS | `/tts-stream` | Text-to-speech streaming |

For full endpoint details, see [docs/API.md](docs/API.md) or visit `/docs` when the server is running.

## Authentication

Most endpoints require a Bearer token in the `Authorization` header:

```
Authorization: Bearer <access_token>
```

Obtain tokens via `POST /api/v1/auth/login`.

## Performance

- Vector search uses MongoDB Atlas Vector Search with cosine similarity
- Response caching via Redis
- Rate limiting per role (admin, teacher, default)
- Optional performance monitoring middleware

## License

MIT
