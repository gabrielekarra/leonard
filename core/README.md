# Leonard Core

The Python engine powering Leonard - the local-first agent. Tool execution is verified and user-facing responses are formatted through a single response layer.

## Setup

```bash
poetry install
# Run the server
poetry run uvicorn leonard.main:app --reload --port 7878
```

## Safety and correctness

- File operations are restricted to your home directory and `/tmp`, and every mutation is verified (exists/moved/deleted) before reporting success.
- Tool results flow through `ResponseFormatter` so user-visible confirmations are derived only from verified `ToolResult` data.
- Destructive operations require either a high-confidence target (explicit path or user selection) or an explicit confirmation step that shows the resolved path.
- If the orchestrator cannot safely resolve a path, it will not run a tool and will ask for a concrete location instead of guessing.

## Testing

```bash
poetry run pytest leonard/tests
```

## Layout

```
leonard/
├── main.py          # FastAPI app entry
├── config.py        # Settings
├── engine/          # Orchestrator, router, response formatting hooks
├── memory/          # Semantic storage (RAG)
├── tools/           # Tool definitions and verified filesystem layer
├── api/             # HTTP endpoints
└── utils/           # Helpers
```
