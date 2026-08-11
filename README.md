# Puter OpenAI Proxy

A lightweight local proxy that exposes [Puter.com](https://puter.com)'s AI models through a standard **OpenAI-compatible API** (`/v1/chat/completions`). Use Puter's free-tier models (Claude, GPT, Qwen, and more) directly from any OpenAI SDK, agent framework, or code editor that supports custom OpenAI-compatible endpoints.

## Recent Changes
* Admin token verification now uses PBKDF2 hash from `admin_token.json` instead of plaintext `ADMIN_TOKEN` in `.env`
* `HOST` and `PORT` are now configurable via `.env` with `HOST` and `PORT` keys
* FastAPI docs/openapi disabled in production: `docs_url=None, redoc_url=None, openapi_url=None`
* `POST /v1/chat/completions` validates request body with Pydantic `ChatCompletionRequest`
* `KeyStore` uses `threading.RLock` for thread-safe file writes and safe window reset handling
* Security hardening: input validation, file lock, admin token hash, no secrets in logs

---

## Table of Contents

- [How It Works](#how-it-works)
- [Supported Features](#supported-features)
- [Available Models](#available-models)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Getting Your Auth Token](#getting-your-auth-token)
- [Configuration](#configuration)
- [Running the Proxy](#running-the-proxy)
- [API Reference](#api-reference)
- [Integration Guides](#integration-guides)
  - [OpenCode](#opencode)
  - [OpenAI Python SDK](#openai-python-sdk)
  - [OpenAI JavaScript SDK](#openai-javascript-sdk)
  - [Continue.dev (VS Code)](#continuedev-vs-code)
  - [Cline (VS Code)](#cline-vs-code)
  - [Cursor](#cursor)
  - [Generic curl](#generic-curl)
- [Error Handling](#error-handling)
- [Troubleshooting](#troubleshooting)
- [Project Structure](#project-structure)
- [Limitations](#limitations)
- [License](#license)

---

## How It Works

```
 Your AI Tool                 Puter Proxy                  Puter API
 (OpenCode, SDK,       (localhost:8000)           (api.puter.com)
  Cursor, etc.)
      |                       |                          |
      |  POST /v1/chat/       |                          |
      |  completions          |                          |
      |  (OpenAI format)      |                          |
      |---------------------->|                          |
      |                       |  POST /drivers/call      |
      |                       |  (Puter driver format)   |
      |                       |------------------------->|
      |                       |                          |
      |                       |  NDJSON stream           |
      |                       |<-------------------------|
      |  SSE stream / JSON    |                          |
      |  (OpenAI format)      |                          |
      |<----------------------|                          |
```

The proxy receives standard OpenAI Chat Completion requests, translates them into Puter's internal driver API format, and translates Puter's NDJSON responses back into OpenAI-compatible SSE streams or JSON responses.

---

## Supported Features

| Feature | Streaming | Non-Streaming | Notes |
|---|:---:|:---:|---|
| **Text content** | Yes | Yes | Standard assistant messages |
| **Tool calls (function calling)** | Yes | Yes | Single and parallel tool calls |
| **Tool call deltas** | Yes | N/A | Incremental argument streaming |
| **Reasoning / thinking** | Yes | Yes | `reasoning_content` field |
| **Structured outputs** | Yes | Yes | `response_format` passthrough |
| **Sampling parameters** | Yes | Yes | `temperature`, `max_tokens`, `top_p`, etc. |
| **Usage statistics** | Yes | Yes | Token counts and cost |
| **Finish reason** | Yes | Yes | `stop`, `tool_calls`, `length`, etc. |
| **Error passthrough** | Yes | Yes | Upstream status codes preserved (402, 429, etc.) |

All standard OpenAI Chat Completion parameters are forwarded transparently to Puter, including: `tools`, `tool_choice`, `response_format`, `temperature`, `max_tokens`, `top_p`, `frequency_penalty`, `presence_penalty`, `stop`, `seed`, and any other parameters Puter supports.

---

## Available Models

The proxy exposes these models by default (configurable in `puter_proxy.py`):

| Model ID | Provider | Description |
|---|---|---|
| `claude-fable-5` | Anthropic | Claude Fable 5 |
| `claude-opus-4-8` | Anthropic | Claude Opus 4.8 |
| `qwen/qwen3.7-max` | Alibaba | Qwen 3.7 Max |

You can use any model available on Puter by specifying its ID in your request. To add models to the `/v1/models` listing, edit the `data` array in the `models()` endpoint.

---

## Prerequisites

- **Python 3.9+**
- **A Puter.com account** (free tier works)
- **A web browser** (for extracting the auth token)

---

## Installation

1. **Clone the repository:**

   ```bash
   git clone https://github.com/YOUR_USERNAME/puter-proxy.git
   cd puter-proxy
   ```

2. **Install Python dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

   Or install manually:

   ```bash
   pip install fastapi uvicorn requests python-dotenv
   ```

---

## Getting Your Auth Token

The proxy needs your Puter auth token to make API calls on your behalf. Here's how to extract it:

### Step 1: Serve the Puter SDK page

From the project directory, start a simple HTTP server:

```bash
python -m http.server 8000
```

### Step 2: Open in your browser

Navigate to:

```
http://localhost:8000
```

This loads the `test_puter.html` page which includes the Puter JS SDK. Wait for the page to fully load.

### Step 3: Extract the token

Open **Developer Tools** (press `F12` or `Ctrl+Shift+I` / `Cmd+Option+I` on Mac), go to the **Console** tab, and run:

```javascript
localStorage.getItem("puter.auth.token.v2")
```

If you are not logged in, Puter will prompt you to sign in first. After signing in, run the command again.

Copy the returned token string.

### Step 4: Set the token

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Then paste your token:

```env
PUTER_TOKEN=your-token-here
```

> **Important:** Never commit your `.env` file or share your token. It is already excluded in `.gitignore`.

---

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|---|:---:|---|---|
| `PUTER_TOKEN` | Yes | - | Your Puter auth token (JWT) |

### Proxy Settings

The proxy runs on:

| Setting | Value |
|---|---|
| **Host** | `0.0.0.0` (all interfaces) |
| **Port** | `8000` |
| **Base URL** | `http://localhost:8000/v1` |

To change the port, edit the last line of `puter_proxy.py`:

```python
uvicorn.run(app, host="0.0.0.0", port=8000)  # change 8000 to your preferred port
```

---

## Running the Proxy

```bash
python puter_proxy.py
```

You should see:

```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

### Verify it's working

```bash
curl http://localhost:8000/v1/models
```

Expected response:

```json
{
  "object": "list",
  "data": [
    {"id": "claude-fable-5", "object": "model", "owned_by": "puter"},
    {"id": "claude-opus-4-8", "object": "model", "owned_by": "puter"},
    {"id": "qwen/qwen3.7-max", "object": "model", "owned_by": "puter"}
  ]
}
```

### Quick chat test

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "claude-opus-4-8",
    "messages": [{"role": "user", "content": "hi"}]
  }'
```

---

## API Reference

### `GET /v1/models`

Returns the list of available models in OpenAI format.

### `POST /v1/chat/completions`

Standard OpenAI Chat Completions endpoint. Accepts all parameters from the [OpenAI Chat Completions API](https://platform.openai.com/docs/api-reference/chat).

#### Request Body

```json
{
  "model": "claude-opus-4-8",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello"}
  ],
  "stream": false,
  "temperature": 0.7,
  "max_tokens": 1024,
  "tools": [...],
  "tool_choice": "auto",
  "response_format": {"type": "json_object"}
}
```

All parameters except `model` and `messages` are optional. Any unrecognized parameters are forwarded to Puter transparently.

#### Non-Streaming Response

```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1781115204,
  "model": "claude-opus-4-8",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello! How can I help?",
        "reasoning_content": "...",
        "tool_calls": [...]
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 12,
    "completion_tokens": 28,
    "cached_tokens": 0,
    "usd_cents": 0.039
  }
}
```

#### Streaming Response (SSE)

When `"stream": true`, the endpoint returns Server-Sent Events:

```
data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1781115204,"model":"claude-opus-4-8","choices":[{"index":0,"delta":{"reasoning_content":"Thinking..."},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1781115204,"model":"claude-opus-4-8","choices":[{"index":0,"delta":{"content":"Hello!"},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1781115204,"model":"claude-opus-4-8","choices":[{"index":0,"delta":{},"finish_reason":"stop"}],"usage":{...}}

data: [DONE]
```

---

## Integration Guides

### OpenCode

Add to your `opencode.config.json`:

```json
{
  "ai": {
    "providers": {
      "puter": {
        "npm": "@ai-sdk/openai-compatible",
        "name": "Puter",
        "options": {
          "baseURL": "http://127.0.0.1:8000/v1",
          "apiKey": "dummy"
        },
        "models": {
          "claude-opus-4-8": {},
          "qwen/qwen3.7-max": {},
          "claude-fable-5": {}
        }
      }
    }
  }
}
```

The `apiKey` value is ignored by the proxy (authentication uses the `.env` token), but some SDKs require it to be set.

### OpenAI Python SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="dummy"
)

# Non-streaming
response = client.chat.completions.create(
    model="claude-opus-4-8",
    messages=[{"role": "user", "content": "Hello"}]
)
print(response.choices[0].message.content)

# Streaming
stream = client.chat.completions.create(
    model="claude-opus-4-8",
    messages=[{"role": "user", "content": "Hello"}],
    stream=True
)
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

### OpenAI JavaScript SDK

```javascript
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "http://localhost:8000/v1",
  apiKey: "dummy",
});

const response = await client.chat.completions.create({
  model: "claude-opus-4-8",
  messages: [{ role: "user", content: "Hello" }],
});

console.log(response.choices[0].message.content);
```

### Continue.dev (VS Code)

Add to your `~/.continue/config.json`:

```json
{
  "models": [
    {
      "title": "Puter Claude Opus",
      "provider": "openai",
      "model": "claude-opus-4-8",
      "apiBase": "http://localhost:8000/v1",
      "apiKey": "dummy"
    },
    {
      "title": "Puter Qwen Max",
      "provider": "openai",
      "model": "qwen/qwen3.7-max",
      "apiBase": "http://localhost:8000/v1",
      "apiKey": "dummy"
    }
  ]
}
```

### Cline (VS Code)

In Cline settings:

1. **API Provider**: Select "OpenAI Compatible"
2. **Base URL**: `http://localhost:8000/v1`
3. **API Key**: `dummy`
4. **Model ID**: `claude-opus-4-8` (or any available model)

### Cursor

In Cursor Settings > Models:

1. Add a new OpenAI-compatible provider
2. **Base URL**: `http://localhost:8000/v1`
3. **API Key**: `dummy`
4. **Model**: `claude-opus-4-8`

### Generic curl

```bash
# Non-streaming
curl -X POST http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "claude-opus-4-8",
    "messages": [{"role": "user", "content": "Explain quantum computing"}]
  }'

# Streaming
curl -X POST http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "claude-opus-4-8",
    "messages": [{"role": "user", "content": "Write a haiku"}],
    "stream": true
  }'

# With tool calls
curl -X POST http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "claude-opus-4-8",
    "messages": [{"role": "user", "content": "What is the weather in London?"}],
    "tools": [{
      "type": "function",
      "function": {
        "name": "get_weather",
        "description": "Get current weather for a location",
        "parameters": {
          "type": "object",
          "properties": {
            "location": {"type": "string"}
          },
          "required": ["location"]
        }
      }
    }]
  }'
```

---

## Error Handling

The proxy passes through Puter's HTTP status codes and error messages:

| Status | Meaning | Example |
|---|---|---|
| `200` | Success | Normal response |
| `402` | Insufficient funds | Puter usage quota exceeded |
| `429` | Rate limited | Too many requests |
| `500` | Server error | Token not configured |
| `502` | Upstream error | Cannot reach Puter API |

### Common Errors

**`PUTER_TOKEN environment variable not set`** (HTTP 500)

Your `.env` file is missing or the token is empty. See [Getting Your Auth Token](#getting-your-auth-token).

**`No usage left for request`** (HTTP 402)

Your Puter account has reached its usage limit for the requested model. Options:
- Wait for the quota to reset
- Switch to a different model
- Upgrade your Puter plan

---

## Troubleshooting

### Proxy won't start

```bash
# Check Python version (need 3.9+)
python --version

# Check dependencies
pip install -r requirements.txt
```

### Token not working

1. Log out and back in at [puter.com](https://puter.com)
2. Re-extract the token using the browser console method
3. Update your `.env` file with the new token

### Model not found

The model list in `/v1/models` is cosmetic. You can request any model available on Puter by specifying its ID directly. If a model returns an error, it may not be available on your Puter plan.

### Streaming not working in your tool

Some tools don't support streaming. Set `"stream": false` in your request, or check your tool's documentation for streaming configuration.

---

## Project Structure

```
puter-proxy/
  puter_proxy.py      # Main proxy server (FastAPI)
  .env                 # Your auth token (not committed)
  .env.example         # Template for .env
  .gitignore           # Git ignore rules
  requirements.txt     # Python dependencies
  test_puter.html      # Helper page for token extraction
  package.json         # Node.js deps (Puter JS SDK for token page)
  README.md            # This file
```

---

## Limitations

- **Single-user**: The proxy is designed for local, single-user use. It uses one auth token for all requests.
- **No authentication**: The proxy has no auth layer. Anyone who can reach `localhost:8000` can make requests. Do not expose it to the internet.
- **Puter rate limits**: Free-tier Puter accounts have usage limits per model. Heavy use (especially with agent frameworks that make many requests) may hit these limits.
- **Model availability**: Available models depend on your Puter account tier. The models listed in `/v1/models` are suggestions; actual availability may vary.

---

## License

MIT
