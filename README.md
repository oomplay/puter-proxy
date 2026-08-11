# Puter OpenAI Proxy - Multi-User

A lightweight local proxy that exposes Puter.com AI models through a standard OpenAI-compatible API (/v1/chat/completions) with multi-user API key support, per-key rate limiting, and an admin API for key management. Use Puter free-tier models directly from any OpenAI SDK, agent framework, or code editor that supports custom OpenAI-compatible endpoints.

## Table of Contents

- How It Works
- Supported Features
- Available Models
- Prerequisites
- Installation
- Getting Your Auth Token
- Configuration
- Running the Proxy
- Admin API
- API Reference
- Integration Guides
- Rate Limiting Details
- Security Notes
- Error Handling
- Troubleshooting
- Project Structure
- Limitations
- License

## How It Works

Your AI Tool -> Puter Proxy -> Puter API
OpenAI format -> translate -> driver format

Public endpoints require Authorization: Bearer <API_KEY>. Each API key maps to a Puter JWT token stored in keys.json. Admin endpoints are protected by ADMIN_TOKEN.

## Supported Features

| Feature | Streaming | Non-Streaming | Notes |
|---|---|---|---|
| Text content | Yes | Yes | Standard assistant messages |
| Tool calls | Yes | Yes | Single and parallel tool calls |
| Tool call deltas | Yes | N/A | Incremental argument streaming |
| Reasoning / thinking | Yes | Yes | reasoning_content field |
| Structured outputs | Yes | Yes | response_format passthrough |
| Sampling parameters | Yes | Yes | temperature, max_tokens, top_p, frequency_penalty, presence_penalty, stop, seed |
| Usage statistics | Yes | Yes | Token counts and cost |
| Finish reason | Yes | Yes | stop, tool_calls, length, etc. |
| Error passthrough | Yes | Yes | Upstream status codes preserved |

## Available Models

The proxy can list models dynamically from Puter via GET /v1/models. Default fallback models:

| Model ID | Provider | Description |
|---|---|---|
| claude-fable-5 | Anthropic | Claude Fable 5 |
| claude-opus-4-8 | Anthropic | Claude Opus 4.8 |
| qwen/qwen3.7-max | Alibaba | Qwen 3.7 Max |

You can request any model available on Puter by specifying its ID.

## Prerequisites

- Python 3.9+
- Puter.com account
- ADMIN_TOKEN for admin API
- Web browser for token extraction

## Installation

```bash
git clone <repo>
cd puter-proxy
pip install -r requirements.txt
```

Requirements: fastapi, uvicorn, httpx, python-dotenv, slowapi, pydantic-settings

## Getting Your Auth Token

1. Serve helper page:
```bash
python -m http.server 8000
```
2. Open http://localhost:8000/test_puter.html
3. Open DevTools Console and run:
```javascript
localStorage.getItem("puter.auth.token.v2")
```
4. Create .env:
```
PUTER_TOKEN=your-token-here
ADMIN_TOKEN=your-admin-secret
HOST=127.0.0.1
PORT=8100
```

Never commit .env or keys.json.

## Configuration

Environment variables:

| Variable | Required | Default | Description |
|---|---|---|---|
| PUTER_TOKEN | No | - | Fallback single Puter JWT |
| ADMIN_TOKEN | Yes | - | Admin API token, stored hashed in admin_token.json |
| HOST | No | 127.0.0.1 | Bind host, localhost allowed without TLS |
| PORT | No | 8100 | Bind port |
| RATE_LIMIT_REQUESTS | No | 60 | Default requests per minute per key |
| KEY_STORE_PATH | No | keys.json | Path to key store |
| SSL_CERTFILE | No | - | Required if HOST not localhost |
| SSL_KEYFILE | No | - | Required if HOST not localhost |
| ALLOWED_ORIGINS | No | [] | CORS origins |

## Running the Proxy

```bash
python puter_proxy.py
```

Health check:
```bash
curl http://127.0.0.1:8100/health
```

Verify models:
```bash
curl -H "Authorization: Bearer sk-xxx" http://127.0.0.1:8100/v1/models
```

## Admin API

All routes prefixed /admin require Authorization: Bearer <ADMIN_TOKEN>

POST /admin/keys - create key
GET /admin/keys - list keys
GET /admin/keys/{key}
PATCH /admin/keys/{key}
DELETE /admin/keys/{key}
POST /admin/keys/{key}/rotate

Example create:
```bash
curl -X POST http://127.0.0.1:8100/admin/keys \
  -H "Authorization: Bearer admin-secret-token" \
  -H "Content-Type: application/json" \
  -d '{"name":"user1","puter_token":"...","rate_limit_requests":60}'
```

## API Reference

GET /v1/models
Returns list of models. Requires API key.

POST /v1/chat/completions
Standard OpenAI endpoint.

Request:
```json
{
  "model": "claude-opus-4-8",
  "messages": [{"role":"user","content":"Hello"}],
  "stream": false,
  "temperature": 0.7,
  "tools": [],
  "response_format": {"type":"json_object"}
}
```

Non-streaming response:
```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "model": "claude-opus-4-8",
  "choices": [{"index":0,"message":{"role":"assistant","content":"..."},"finish_reason":"stop"}],
  "usage": {"prompt_tokens":12,"completion_tokens":28}
}
```

Streaming returns SSE: data: {...} and data: [DONE]

## Integration Guides

OpenCode
Use baseURL http://127.0.0.1:8100/v1 and apiKey sk-xxx

OpenAI Python SDK
```python
from openai import OpenAI
client = OpenAI(base_url="http://127.0.0.1:8100/v1", api_key="sk-xxx")
response = client.chat.completions.create(model="claude-opus-4-8", messages=[{"role":"user","content":"Hi"}])
```

OpenAI JavaScript SDK
```javascript
import OpenAI from "openai";
const client = new OpenAI({baseURL:"http://127.0.0.1:8100/v1", apiKey:"sk-xxx"});
```

Continue.dev, Cline, Cursor: set base URL and API key to sk-xxx

Generic curl:
```bash
curl -X POST http://127.0.0.1:8100/v1/chat/completions \
  -H "Authorization: Bearer sk-xxx" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen-flash","messages":[{"role":"user","content":"hi"}],"stream":false}'
```

## Rate Limiting Details

Per-key request count uses 60 second sliding window. On each request:
- If window expired, count resets to 0
- If count >= limit, return 429
- Otherwise increment and allow

Limit can be set per key via rate_limit_requests or globally via RATE_LIMIT_REQUESTS.

## Security Notes

- Store .env and keys.json outside version control
- ADMIN_TOKEN is hashed with PBKDF2-HMAC-SHA256 and stored in admin_token.json
- Do not expose proxy to internet without TLS and additional auth
- API keys are bearer tokens, treat as secrets

## Error Handling

| Status | Meaning |
|---|---|
| 200 | Success |
| 401 | Missing/invalid API key |
| 403 | Invalid admin token |
| 402 | Insufficient funds |
| 429 | Rate limited |
| 500 | Server error |
| 502 | Upstream error |

## Troubleshooting

Proxy won't start: check python version and dependencies
Token not working: re-extract token and update .env
Model not found: request any Puter model ID directly
Streaming not working: set "stream": false
429 errors: wait for window reset or increase rate_limit_requests

## Project Structure

puter_proxy.py - FastAPI app
config.py - Settings
auth.py - API key verification & rate limiting
key_store.py - Persistent key store
admin.py - Admin router
puter_client.py - Puter driver client
models.py - Pydantic models
keys.json - API key metadata
test_puter.html - Helper for token extraction
.env - Secrets

## Limitations

- Single process, file-based key store
- No encryption at rest
- For local use only

## License

MIT
