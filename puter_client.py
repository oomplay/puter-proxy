import httpx
import json
import uuid
import time
from typing import AsyncGenerator, Dict, Any, Optional


PUTER_API = "https://api.puter.com/drivers/call"


class PuterClient:
    def __init__(self, token: str, timeout: float = 300.0):
        self.token = token
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.client.aclose()

    def _build_request(self, method: str, args: Dict) -> Dict:
        return {
            "interface": "puter-chat-completion",
            "driver": "ai-chat",
            "method": method,
            "test_mode": False,
            "auth_token": self.token,
            "args": args,
        }

    async def list_models(self) -> list:
        resp = await self.client.post(
            PUTER_API,
            json=self._build_request("models", {}),
            headers={"Content-Type": "text/plain;actually=json"},
        )
        resp.raise_for_status()
        data = resp.json()
        result = data.get("result", [])

        models = []
        for m in result:
            if isinstance(m, str):
                models.append({"id": m, "object": "model", "owned_by": "puter"})
            elif isinstance(m, dict):
                model_id = m.get("id") or m.get("puterId") or m.get("model")
                if model_id:
                    models.append({"id": model_id, "object": "model", "owned_by": "puter"})
        return models

    async def chat_completion_stream(
        self,
        args: Dict
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream chat completion from Puter."""
        args = {**args, "stream": True}

        async with self.client.stream(
            "POST",
            PUTER_API,
            json=self._build_request("complete", args),
            headers={"Content-Type": "text/plain;actually=json"},
        ) as resp:
            resp.raise_for_status()

            async for line in resp.aiter_lines():
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue

    async def chat_completion(
        self,
        args: Dict
    ) -> Dict[str, Any]:
        """Non-streaming chat completion (collect all events)."""
        full_content = ""
        tool_calls = []
        reasoning_content = ""
        usage = None
        finish_reason = "stop"
        tool_call_started = False

        async for event in self.chat_completion_stream(args):
            event_type = event.get("type", event.get("event", ""))

            if event_type in ("text", "content", "message"):
                text = event.get("text", event.get("content", event.get("message", "")))
                if text:
                    full_content += text

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
                tool_calls.append(tc)

            elif event_type == "tool_call_delta":
                tool_call_started = True

            elif event_type in ("reasoning", "thinking"):
                reasoning_text = event.get("reasoning", event.get("text", event.get("content", "")))
                if reasoning_text:
                    reasoning_content += reasoning_text

            elif event_type == "usage":
                usage = event.get("usage", event)

            elif event_type in ("done", "finish"):
                finish_reason = event.get("finish_reason", "tool_calls" if tool_call_started else "stop")
                break

        choice = {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": full_content if full_content else None,
            },
            "finish_reason": finish_reason,
        }

        if tool_calls:
            choice["message"]["tool_calls"] = tool_calls
        if reasoning_content:
            choice["message"]["reasoning_content"] = reasoning_content

        return {
            "id": f"chatcmpl-{uuid.uuid4().hex}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": args.get("model", "claude-fable-5"),
            "choices": [choice],
            "usage": usage,
        }
