"""Puter OpenAI Proxy – multi‑user, API‑key protected, rate‑limited.

The original single‑user implementation has been refactored to:
* Require an ``Authorization: Bearer <api_key>`` header for all public endpoints.
* Support multiple API keys, each mapping to a Puter JWT token.
* Enforce per‑key request rate limits using ``slowapi``.
* Provide an admin API (protected by a separate ADMIN_TOKEN) to create, list,
  update, delete and rotate API keys at runtime.
* Use an async HTTP client (httpx) for non‑blocking calls to Puter.
"""

import os
import json
import time
import uuid
from typing import Dict

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Depends, HTTPException, status, Body
from fastapi.responses import JSONResponse, StreamingResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

# Local modules
from config import settings, limiter
from auth import (
    get_puter_token,
    verify_api_key,
    default_rate_limit,
    verify_admin_token,
)
from puter_client import PuterClient
from admin import router as admin_router
from models import ChatCompletionRequest

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

app = FastAPI(title="Puter OpenAI Proxy", version="2.0.0", docs_url=None, redoc_url=None, openapi_url=None)

# Attach the rate‑limiter middleware
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Include admin routes (protected by ADMIN_TOKEN)
app.include_router(admin_router)


def sse_chunk(data: dict) -> str:
    """Wrap a dict into an SSE ``data: `` line with proper newline termination."""
    return f"data: {json.dumps(data)}\n\n"


def build_completion_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex}"


# ---------------------------------------------------------------------------
# Helper to fetch model list (dynamic) via Puter API
# ---------------------------------------------------------------------------
async def fetch_models(token: str) -> list:
    async with PuterClient(token) as client:
        try:
            models = await client.list_models()
            return models
        except Exception:
            # Fallback to hard‑coded list on any error
            return None


# ---------------------------------------------------------------------------
# Public endpoints (require API key)
# ---------------------------------------------------------------------------
FALLBACK_MODELS = [
    {"id": "claude-fable-5", "object": "model", "owned_by": "puter"},
    {"id": "claude-opus-4-8", "object": "model", "owned_by": "puter"},
    {"id": "qwen/qwen3.7-max", "object": "model", "owned_by": "puter"},
]


@app.get("/v1/models")
async def list_models(
    token: str = Depends(get_puter_token),
    _: None = Depends(default_rate_limit),
):
    """Return a list of available models.

    First tries to retrieve the list from Puter. If the request fails, it falls back
    to a minimal hard‑coded list so the endpoint never returns an error.
    """
    dynamic = await fetch_models(token)
    if dynamic:
        return {"object": "list", "data": dynamic}
    return {"object": "list", "data": FALLBACK_MODELS}


@app.post("/v1/chat/completions")
async def chat_completions(
    body: ChatCompletionRequest = Body(...),
    token: str = Depends(get_puter_token),
    _: None = Depends(default_rate_limit),
):
    """Proxy a Chat Completion request to Puter.

    The request body follows the OpenAI schema. We translate it to Puter's driver
    format, forward it (always streaming from Puter), and then re‑emit either a
    streaming SSE response or a non‑streaming JSON response depending on the
    ``stream`` flag supplied by the client.
    """
    model = body.model
    messages = [m.model_dump() for m in body.messages]
    stream = bool(body.stream)

    # Build arguments for Puter – copy everything except OpenAI‑specific keys.
    body_dict = body.model_dump(exclude_unset=True)
    puter_args: Dict = {k: v for k, v in body_dict.items() if k not in ("model", "messages", "stream")}
    puter_args["model"] = model
    puter_args["messages"] = messages
    puter_args["stream"] = True  # Puter always streams; we aggregate later if needed.

    async with PuterClient(token) as client:
        try:
            if not stream:
                # Non‑streaming – collect all events and return a single JSON payload.
                result = await client.chat_completion(puter_args)
                return JSONResponse(content=result)

            # -------- Streaming response --------
            async def event_generator():
                completion_id = build_completion_id()
                created_ts = int(time.time())
                tool_call_started = False
                sent_finish = False
                usage = None

                async for event in client.chat_completion_stream(puter_args):
                    event_type = event.get("type", event.get("event", ""))

                    if event_type in ("text", "content", "message"):
                        text = event.get("text", event.get("content", event.get("message", "")))
                        if not text:
                            continue
                        yield sse_chunk({
                            "id": completion_id,
                            "object": "chat.completion.chunk",
                            "created": created_ts,
                            "model": model,
                            "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
                        })

                    elif event_type in ("tool_call", "function_call"):
                        tool_call_started = True
                        tc = {
                            "index": event.get("index", 0),
                            "id": event.get("id", f"call_{uuid.uuid4().hex[:24]}"),
                            "type": "function",
                            "function": {
                                "name": event.get("name", event.get("function", {}).get("name", "")),
                                "arguments": event.get("arguments", event.get("function", {}).get("arguments", "")),
                            },
                        }
                        yield sse_chunk({
                            "id": completion_id,
                            "object": "chat.completion.chunk",
                            "created": created_ts,
                            "model": model,
                            "choices": [{"index": 0, "delta": {"tool_calls": [tc]}, "finish_reason": None}],
                        })

                    elif event_type == "tool_call_delta":
                        tool_call_started = True
                        tc_delta = {"index": event.get("index", 0)}
                        fn = {}
                        if "arguments" in event:
                            fn["arguments"] = event["arguments"]
                        if "name" in event:
                            fn["name"] = event["name"]
                        if fn:
                            tc_delta["function"] = fn
                        yield sse_chunk({
                            "id": completion_id,
                            "object": "chat.completion.chunk",
                            "created": created_ts,
                            "model": model,
                            "choices": [{"index": 0, "delta": {"tool_calls": [tc_delta]}, "finish_reason": None}],
                        })

                    elif event_type in ("reasoning", "thinking"):
                        reasoning_text = event.get("reasoning", event.get("text", event.get("content", "")))
                        if not reasoning_text:
                            continue
                        yield sse_chunk({
                            "id": completion_id,
                            "object": "chat.completion.chunk",
                            "created": created_ts,
                            "model": model,
                            "choices": [{
                                "index": 0,
                                "delta": {"reasoning_content": reasoning_text},
                                "finish_reason": None,
                            }],
                        })

                    elif event_type == "usage":
                        usage = event.get("usage", event)

                    elif event_type in ("done", "finish"):
                        reason = event.get("finish_reason", "tool_calls" if tool_call_started else "stop")
                        sent_finish = True
                        yield sse_chunk({
                            "id": completion_id,
                            "object": "chat.completion.chunk",
                            "created": created_ts,
                            "model": model,
                            "choices": [{"index": 0, "delta": {}, "finish_reason": reason}],
                        })
                        break

                # If Puter never sent a final ``done`` event, synthesize one.
                if not sent_finish:
                    reason = "tool_calls" if tool_call_started else "stop"
                    final_chunk = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created_ts,
                        "model": model,
                        "choices": [{"index": 0, "delta": {}, "finish_reason": reason}],
                    }
                    if usage:
                        final_chunk["usage"] = usage
                    yield sse_chunk(final_chunk)

                # End‑of‑stream marker required by OpenAI clients
                yield "data: [DONE]\n\n"

            return StreamingResponse(event_generator(), media_type="text/event-stream")

        except httpx.HTTPStatusError as exc:
            # Upstream returned an HTTP error – forward the details.
            error_body = exc.response.text[:500]
            try:
                upstream = exc.response.json()
                err = upstream.get("error", upstream)
                if isinstance(err, dict):
                    error_content = {"error": err}
                else:
                    error_content = {"error": {"message": str(err), "type": upstream.get("code", "upstream_error")}}
            except (ValueError, AttributeError):
                error_content = {"error": {"message": f"Puter API error: {error_body}", "type": "upstream_error"}}
            return JSONResponse(status_code=exc.response.status_code, content=error_content)

        except httpx.RequestError as exc:
            return JSONResponse(
                status_code=502,
                content={"error": {"message": f"Upstream connection failed: {exc}", "type": "upstream_error"}},
            )


# Simple health probe
@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}


if __name__ == "__main__":
    uvicorn.run(app, host=settings.host, port=settings.port)
