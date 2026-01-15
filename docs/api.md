# Lokus API Documentation

Base URL: `http://localhost:7878/api`

## Endpoints

### Health

#### GET /health
Check if the core is running.

**Response:**
```json
{
  "status": "ok",
  "version": "0.1.0"
}
```

---

### Chat

#### POST /chat
Send a message and receive an AI response.

**Request:**
```json
{
  "message": "Hello, Lokus!",
  "conversation_id": "optional-uuid"
}
```

**Response:**
```json
{
  "id": "uuid",
  "content": "Hello! How can I help you today?",
  "role": "assistant"
}
```

---

### Models

#### GET /models
List all available AI models.

**Response:**
```json
[
  {
    "id": "llama-3.2-3b",
    "name": "Llama 3.2 3B",
    "description": "Fast, general purpose",
    "size": "2.1 GB",
    "installed": true
  },
  {
    "id": "mistral-7b",
    "name": "Mistral 7B",
    "description": "Balanced performance",
    "size": "4.1 GB",
    "installed": false
  }
]
```

#### POST /models/{id}/install
Install a model.

**Response:**
```json
{
  "success": true,
  "message": "Model llama-3.2-3b installed successfully"
}
```

#### DELETE /models/{id}
Remove an installed model.

**Response:**
```json
{
  "success": true,
  "message": "Model llama-3.2-3b removed successfully"
}
```

---

### Tools

#### GET /tools
List all available MCP tools.

**Response:**
```json
[
  {
    "id": "filesystem",
    "name": "Filesystem",
    "description": "Read and write local files",
    "icon": "folder",
    "enabled": true
  },
  {
    "id": "terminal",
    "name": "Terminal",
    "description": "Execute shell commands",
    "icon": "terminal",
    "enabled": false
  }
]
```

#### PUT /tools/{id}
Toggle a tool on or off.

**Request:**
```json
{
  "enabled": true
}
```

**Response:**
```json
{
  "success": true,
  "message": "Tool filesystem enabled"
}
```

---

### Skills

#### GET /skills
List all available skills.

**Response:**
```json
[
  {
    "id": "summarizer",
    "name": "Summarizer",
    "description": "Summarize documents and text",
    "active": true
  },
  {
    "id": "translator",
    "name": "Translator",
    "description": "Translate between languages",
    "active": false
  }
]
```

---

## Error Handling

All errors return appropriate HTTP status codes:

- `400` - Bad Request (invalid input)
- `404` - Not Found (resource doesn't exist)
- `500` - Internal Server Error

Error response format:
```json
{
  "detail": "Error message here"
}
```
