"""Configuration and global objects for Puter OpenAI Proxy.

The settings are loaded from environment variables (or a ``.env`` file) using
``pydantic-settings``. This module also creates a global ``limiter`` instance
from ``slowapi`` which is used throughout the project to enforce per‑key rate
limits.
"""

import json
from typing import Dict, List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings

# SlowAPI rate limiting utilities
from slowapi import Limiter
from slowapi.util import get_remote_address


class Settings(BaseSettings):
    # API Keys mapping: {"sk-xxx": "puter-jwt-token", ...}
    api_keys_json: str = Field(default="{}", alias="API_KEYS")

    # Fallback single token (backward compatibility)
    puter_token: str = Field(default="", alias="PUTER_TOKEN")

    # Server configuration
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8100, alias="PORT")

    # Rate limiting defaults (requests per minute)
    rate_limit_requests: int = 60
    rate_limit_tokens: int = 100_000

    # Admin token (protects admin endpoints)
    admin_token: str = Field(default="", alias="ADMIN_TOKEN")

    # Path to the JSON file that stores API key metadata
    key_store_path: str = "keys.json"

    # ---------------------------------------------------------------------
    # TLS / HTTPS configuration (required for public exposure)
    # ---------------------------------------------------------------------
    ssl_certfile: Optional[str] = Field(default=None, alias="SSL_CERTFILE")
    ssl_keyfile: Optional[str] = Field(default=None, alias="SSL_KEYFILE")

    # Allowed CORS origins – empty list disables CORS (default for server‑to‑server API).
    allowed_origins: List[str] = Field(default_factory=list, alias="ALLOWED_ORIGINS")

    @property
    def api_keys(self) -> Dict[str, str]:
        """Parse ``api_keys_json`` into a dictionary.

        The value can be a JSON object mapping API keys to Puter tokens or a
        simple comma‑separated list of keys (legacy format). In the latter case
        all keys map to the single ``puter_token`` defined above.
        """
        try:
            return json.loads(self.api_keys_json)
        except json.JSONDecodeError:
            # Legacy comma‑separated format
            if self.api_keys_json and not self.api_keys_json.startswith("{"):
                return {k.strip(): self.puter_token for k in self.api_keys_json.split(",") if k.strip()}
            return {}

    class Config:
        env_file = ".env"
        case_sensitive = False


# Global rate limiter instance – uses client IP address by default.
limiter = Limiter(key_func=get_remote_address)

# Create a singleton ``settings`` object for convenient import elsewhere.
settings = Settings()

# ---------------------------------------------------------------------
# Runtime TLS validation
# ---------------------------------------------------------------------
def _validate_tls_settings() -> None:
    """Ensure that TLS is configured when the service is bound to a public address.

    For a development environment bound to ``127.0.0.1`` we allow plain HTTP.
    If ``settings.host`` is any other value (e.g. ``0.0.0.0``) the proxy must be
    started with both ``ssl_certfile`` and ``ssl_keyfile`` defined, otherwise a
    ``RuntimeError`` is raised and the application will not start.
    """
    if settings.host not in ("127.0.0.1", "localhost"):
        if not settings.ssl_certfile or not settings.ssl_keyfile:
            raise RuntimeError(
                "TLS is required for public deployment – set SSL_CERTFILE and SSL_KEYFILE environment variables"
            )

_validate_tls_settings()
