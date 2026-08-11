"""Authentication and rate?limiting utilities for the Puter proxy.

All public endpoints require an ``Authorization: Bearer <API_KEY>`` header. The
provided API key is validated against the persistent ``KeyStore``. If valid, the
associated Puter JWT token is returned via the ``get_puter_token`` dependency.

Rate limiting is handled per?key using ``slowapi``. ``create_rate_limiter``
produces a FastAPI dependency that enforces a request limit (defaulting to the
global setting but allowing per?key overrides stored in the ``KeyStore``).

Admin routes are protected by a single shared ``ADMIN_TOKEN`` defined in the
environment. ``verify_admin_token`` validates the ``Authorization`` header
against this token.
"""

from fastapi import Depends, Header, HTTPException, Request, status
from slowapi import Limiter
from typing import Callable

import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path

from config import settings, limiter
from key_store import KeyStore

key_store = KeyStore(settings.key_store_path)

ADMIN_TOKEN_FILE = Path(os.getenv("ADMIN_TOKEN_FILE", "admin_token.json"))

def _load_admin_token() -> tuple[str, bytes]:
    if ADMIN_TOKEN_FILE.exists():
        data = json.loads(ADMIN_TOKEN_FILE.read_text(encoding="utf-8"))
        return data["hash"], bytes.fromhex(data["salt"])
    raw = os.getenv("ADMIN_TOKEN")
    if not raw:
        raise RuntimeError("ADMIN_TOKEN environment variable is required for first run")
    salt = secrets.token_bytes(16)
    hash_ = hashlib.pbkdf2_hmac("sha256", raw.encode(), salt, 200_000).hex()
    tmp_path = ADMIN_TOKEN_FILE.with_suffix('.tmp')
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump({"hash": hash_, "salt": salt.hex()}, f)
    os.replace(tmp_path, ADMIN_TOKEN_FILE)
    return hash_, salt

ADMIN_TOKEN_HASH, ADMIN_TOKEN_SALT = _load_admin_token()

async def verify_api_key(authorization: str = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header. Use: Bearer sk-xxx",
            headers={"WWW-Authenticate": "Bearer"},
        )
    api_key = authorization[7:]
    entry = key_store.get(api_key)
    if not entry or not getattr(entry, "is_active", False):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return api_key

async def get_puter_token(api_key: str = Depends(verify_api_key)) -> str:
    token = key_store.get_puter_token(api_key)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No Puter token configured for this API key",
        )
    return token

def create_rate_limiter(requests: int = None, tokens: int = None) -> Callable:
    async def rate_limit_dep(api_key: str = Depends(verify_api_key)):
        key_req_limit, _ = key_store.get_rate_limits(api_key)
        limit_val = requests or key_req_limit or settings.rate_limit_requests
        allowed = key_store.try_consume(api_key, int(limit_val))
        if not allowed:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        return None
    return rate_limit_dep

default_rate_limit = create_rate_limiter()

async def verify_admin_token(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization[7:]
    # Verify against hashed admin token if file exists, fallback to env for first run
    if ADMIN_TOKEN_HASH and ADMIN_TOKEN_SALT:
        test_hash = hashlib.pbkdf2_hmac("sha256", token.encode(), ADMIN_TOKEN_SALT, 200_000).hex()
        if not hmac.compare_digest(test_hash, ADMIN_TOKEN_HASH):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid admin token")
    else:
        admin_token = settings.admin_token
        if not admin_token:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Admin API not configured",
            )
        if token != admin_token:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid admin token")
    return token
