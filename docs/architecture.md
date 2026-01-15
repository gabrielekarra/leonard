# Lokus Architecture

## Overview

Lokus is built on a client-server architecture where a native macOS app (SwiftUI) communicates with a Python backend (FastAPI) over HTTP.

## Components

### Desktop App (SwiftUI)

The macOS app provides the user interface with two main views:

1. **askLokus** - Chat interface for conversing with AI
2. **AIs** - Management of models, tools, and skills

#### Key Files

- `LokusApp.swift` - App entry point
- `MainView.swift` - Root view with navigation
- `ChatViewModel.swift` - Chat state management
- `AIsViewModel.swift` - AI resources state management
- `CoreAPI.swift` - HTTP client for backend communication

#### Design Patterns

- **MVVM Architecture**: Views observe ViewModels using `@Observable`
- **Async/Await**: All network calls use Swift concurrency
- **Actor Isolation**: `CoreAPI` is an actor for thread-safe API calls

### Python Core (FastAPI)

The backend provides REST APIs and will eventually handle:

- Model inference
- Memory/RAG operations
- MCP tool execution

#### Key Modules

- `main.py` - FastAPI app with route registration
- `engine/` - AI orchestration and model management
- `memory/` - Semantic storage and retrieval
- `mcp/` - Model Context Protocol integration
- `api/` - HTTP endpoints and schemas

## Communication Flow

```
┌──────────────┐         HTTP         ┌──────────────┐
│              │  ───────────────────>│              │
│  SwiftUI     │                      │   FastAPI    │
│  Frontend    │  <───────────────────│   Backend    │
│              │         JSON         │              │
└──────────────┘                      └──────────────┘
```

### API Contract

All communication uses JSON over HTTP:

- **Base URL**: `http://localhost:7878/api`
- **Content-Type**: `application/json`
- **Error Handling**: HTTP status codes + error messages

## Data Models

### Message
```swift
struct Message {
    let id: String
    let content: String
    let role: MessageRole  // .user or .assistant
    let timestamp: Date
}
```

### AIModel
```swift
struct AIModel {
    let id: String
    let name: String
    let description: String
    let size: String
    var installed: Bool
}
```

### Tool
```swift
struct Tool {
    let id: String
    let name: String
    let description: String
    let icon: String
    var enabled: Bool
}
```

## Future Architecture

### Phase 2: Real AI Integration

```
Desktop App
    │
    ├── HTTP ──> FastAPI ──> Ollama (model inference)
    │                   ├──> LanceDB (vector storage)
    │                   └──> MCP Servers (tool execution)
    │
    └── Direct Process Communication (optional optimization)
```

### Planned Features

1. **Model Inference**: Integrate with Ollama for local LLM execution
2. **RAG Pipeline**: LanceDB for vector storage, local embeddings
3. **MCP Integration**: Connect to filesystem, terminal, browser tools
4. **Permission System**: User approval for sensitive tool actions

## Security Considerations

- All data stays local - no cloud uploads
- Tool execution requires explicit user permission
- Sensitive operations logged for audit trail
- Network requests limited to localhost by default
