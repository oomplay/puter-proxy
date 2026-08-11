# Puter OpenAI Proxy - Multi-User

A lightweight local proxy that exposes Puter.com AI models through a standard OpenAI-compatible API (`/v1/chat/completions`) with multi-user API key support, per-key rate limiting, and an admin API for key management.

## How It Works

```
Your AI Tool -> Puter Proxy -> Puter API
OpenAI format -> translate -> driver format
```

Public endpoints require `Authorization: Bearer <API_KEY>`. Each API key maps to a Puter JWT token stored in `keys.json`. Admin endpoints are protected by `ADMIN_TOKEN`.

## Features

* OpenAI-compatible `/v1/models` and `/v1/chat/completions` with streaming and non-streaming
* Per-API-key rate limiting with 60 second sliding window
* Admin API to create/list/update/delete/rotate API keys at runtime
* Tool calls, reasoning content, structured outputs passthrough
* Usage statistics and finish reason passthrough

## Prerequisites

* Python 3.9+
* Puter.com account
* `ADMIN_TOKEN` for admin API

## Installation

```bash
git clone <repo>
cd puter-proxy
pip install -r requirements.txt
```

## Configuration

Create `.env`:

```
PUTER_TOKEN=your-puter-jwt  # fallback single token
ADMIN_TOKEN=your-admin-secret
HOST=127.0.0.1
PORT=8100
# Optional: API_KEYS_JSON, RATE_LIMIT_REQUESTS, KEY_STORE_PATH, etc.
```

The proxy stores API keys in `keys.json`. Never commit `.env` or `keys.json`.

## Running

```bash
python puter_proxy.py
```

Health check:
```bash
curl http://127.0.0.1:8100/health
```

## Admin API

All admin routes are prefixed `/admin` and require `Authorization: Bearer <ADMIN_TOKEN>`.

* `POST /admin/keys` - create key
```json
{"name":"user1","puter_token":"...","rate_limit_requests":60}
```
* `GET /admin/keys` - list keys
* `GET /admin/keys/{key}`
* `PATCH /admin/keys/{key}` - update name/token/limits/active
* `DELETE /admin/keys/{key}`
* `POST /admin/keys/{key}/rotate` - rotate key

Example:
```bash
curl -X POST http://127.0.0.1:8100/admin/keys \
  -H "Authorization: Bearer admin-secret-token" \
  -H "Content-Type: application/json" \
  -d '{"name":"test","puter_token":"..."}'
```

## Public API

All public endpoints require `Authorization: Bearer <API_KEY>`.

`GET /v1/models`
`POST /v1/chat/completions`

Example:
```bash
curl http://127.0.0.1:8100/v1/models \
  -H "Authorization: Bearer sk-xxx"
```

Chat:
```bash
curl -X POST http://127.0.0.1:8100/v1/chat/completions \
  -H "Authorization: Bearer sk-xxx" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen-flash","messages":[{"role":"user","content":"hi"}],"stream":false}'
```

## Integration

Use any OpenAI-compatible SDK with:
* `base_url: http://127.0.0.1:8100/v1`
* `api_key: sk-xxx`  # your API key, dummy value also accepted by some SDKs

## Rate Limiting

Per-key request count resets every 60 seconds. Default limit is 60 requests/minute, configurable per key and via `RATE_LIMIT_REQUESTS`.

## Project Structure

```
puter_proxy.py   # FastAPI app
config.py        # Settings
auth.py          # API key verification & rate limiting
key_store.py     # Persistent key store
admin.py         # Admin router
puter_client.py  # Puter driver client
models.py        # Pydantic models
keys.json        # API key metadata
```

## Limitations

* Single process, file-based key store
* No encryption at rest for keys/tokens
* For local use only, do not expose publicly without TLS and auth hardening
