# Lokus

**The local-first engine to build and run private AI agents to automate your workflow.**

Lokus is an open-source, local-first AI orchestrator that gives you total control over your data and productivity. Turn your computer into an autonomous agent capable of reasoning (SLM), remembering (Semantic Memory), and acting on external software (MCP), without ever sending sensitive data to the cloud.

**Tagline:** Modular. Orchestrate. Remember. Act.

## Features

### The Brain — Modular SLM Orchestration
- Load and run local language models (Llama, Mistral, Phi, etc.)
- Support for multiple specialized models
- Optimized execution on local hardware (CPU/GPU/NPU)

### The Memory — Local Semantic Vault
- RAG (Retrieval-Augmented Generation) running entirely locally
- Automatic indexing of user documents, chats, files
- Persistent context across sessions

### The Hands — MCP Integration
- Native support for Model Context Protocol (MCP)
- Connect to external tools: filesystem, terminal, browser, and more
- Granular permission system

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    LOKUS DESKTOP APP                        │
│                    (macOS Native - SwiftUI)                 │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────────────────────────────┐   │
│  │   Sidebar   │  │            Content Area             │   │
│  │             │  │                                     │   │
│  │  askLokus   │  │   [Tab 1: Chat Interface]           │   │
│  │     ○       │  │   [Tab 2: AIs Management]           │   │
│  │             │  │                                     │   │
│  │    AIs      │  │                                     │   │
│  │     ○       │  │                                     │   │
│  └─────────────┘  └─────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ HTTP (localhost:7878)
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      LOKUS CORE                             │
│                      (Python Engine)                        │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   Engine    │  │   Memory    │  │    MCP Client       │  │
│  │             │  │   (Vault)   │  │                     │  │
│  │ - Chat      │  │             │  │ - Tool Registry     │  │
│  │ - Orchestr. │  │ - Index     │  │ - Permission Mgmt   │  │
│  │ - Model Mgr │  │ - Search    │  │ - Action Execution  │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- macOS 14.0+ (Sonoma or later)
- Python 3.11+
- Xcode 15+
- Poetry (optional, for Python package management)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/lokus.git
   cd lokus
   ```

2. **Install Python dependencies**

   Using virtual environment (recommended):
   ```bash
   make setup-venv
   ```

   Or using Poetry:
   ```bash
   make install
   ```

3. **Start the Python core**

   Using virtual environment:
   ```bash
   make core-venv
   ```

   Or using Poetry:
   ```bash
   make core
   ```

4. **Build and run the macOS app**
   ```bash
   cd apps/desktop
   open Lokus.xcodeproj
   ```
   Then press Cmd+R to build and run in Xcode.

### Verify Installation

Once both the core and app are running:
- The Python core should be accessible at `http://localhost:7878`
- Health check: `curl http://localhost:7878/api/health`
- The macOS app should show "Lokus Core is not running" banner if the core is down

## Project Structure

```
lokus/
├── README.md
├── LICENSE                    # MIT License
├── Makefile                   # Build commands
│
├── apps/
│   └── desktop/               # macOS native app (SwiftUI)
│       ├── Lokus.xcodeproj
│       └── Lokus/
│           ├── LokusApp.swift
│           ├── Config/
│           ├── Views/
│           ├── Models/
│           ├── ViewModels/
│           └── Services/
│
├── core/                      # Python engine (FastAPI)
│   ├── pyproject.toml
│   └── lokus/
│       ├── main.py
│       ├── config.py
│       ├── engine/
│       ├── memory/
│       ├── mcp/
│       └── api/
│
├── shared/                    # Shared assets
│   └── icons/
│
└── docs/
    └── architecture.md
```

## API Reference

### Health Check
```
GET /api/health
Response: { "status": "ok", "version": "0.1.0" }
```

### Chat
```
POST /api/chat
Request:  { "message": "string", "conversation_id": "string?" }
Response: { "id": "string", "content": "string", "role": "assistant" }
```

### Models
```
GET /api/models                    # List all models
POST /api/models/{id}/install      # Install a model
DELETE /api/models/{id}            # Remove a model
```

### Tools
```
GET /api/tools                     # List all tools
PUT /api/tools/{id}                # Toggle tool (body: { "enabled": bool })
```

### Skills
```
GET /api/skills                    # List all skills
```

## Development

### Running Tests

```bash
cd core
poetry run pytest
```

### Code Style

- **Swift**: SwiftUI with MVVM architecture
- **Python**: Type hints, async/await, Pydantic models

## Contributing

Contributions are welcome! Please read our contributing guidelines before submitting PRs.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Roadmap

- [ ] Real model inference (Ollama integration)
- [ ] MCP protocol implementation
- [ ] RAG with LanceDB
- [ ] Multiple conversation support
- [ ] Light mode
- [ ] Settings/preferences
- [ ] File upload for indexing
