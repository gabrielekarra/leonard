# Lokus Core

The Python engine powering Lokus - a local-first AI orchestrator.

## Setup

```bash
# Install dependencies
poetry install

# Run the server
poetry run uvicorn lokus.main:app --reload --port 7878
```

## API Endpoints

- `GET /api/health` - Health check
- `POST /api/chat` - Send a chat message
- `GET /api/models` - List available models
- `POST /api/models/{id}/install` - Install a model
- `DELETE /api/models/{id}` - Remove a model
- `GET /api/tools` - List available tools
- `PUT /api/tools/{id}` - Toggle a tool
- `GET /api/skills` - List available skills

## Architecture

```
lokus/
├── main.py          # FastAPI app entry
├── config.py        # Settings
├── engine/          # AI orchestration
├── memory/          # Semantic storage (RAG)
├── mcp/             # Model Context Protocol
├── api/             # HTTP endpoints
└── utils/           # Helpers
```
