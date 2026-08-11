from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


# Admin API Models
class APIKeyCreate(BaseModel):
    name: str = Field(..., description="Human-readable name")
    puter_token: str = Field(..., description="Puter JWT token for this key")
    rate_limit_requests: Optional[int] = None
    rate_limit_tokens: Optional[int] = None


class APIKeyResponse(BaseModel):
    key: str = Field(..., description="The API key (sk-xxx)")
    name: str
    created_at: datetime
    last_used: Optional[datetime] = None
    request_count: int = 0
    is_active: bool = True
    rate_limit_requests: Optional[int] = None
    rate_limit_tokens: Optional[int] = None


class APIKeyUpdate(BaseModel):
    name: Optional[str] = None
    puter_token: Optional[str] = None
    rate_limit_requests: Optional[int] = None
    rate_limit_tokens: Optional[int] = None
    is_active: Optional[bool] = None


# Chat Completion Models (OpenAI compatible)
class ChatMessage(BaseModel):
    role: str
    content: Optional[str] = None
    tool_calls: Optional[List[Dict]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    stream: bool = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    tools: Optional[List[Dict]] = None
    tool_choice: Optional[Any] = None
    response_format: Optional[Dict] = None
    seed: Optional[int] = None
    stop: Optional[List[str]] = None
    user: Optional[str] = None