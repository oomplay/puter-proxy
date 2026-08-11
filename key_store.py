import json
import os
import threading
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime, timedelta

from models import APIKeyResponse, APIKeyCreate, APIKeyUpdate
import secrets

class KeyStore:
    def __init__(self, path: str = "keys.json"):
        self.path = Path(path)
        self._data: Dict = {}
        self._lock = threading.RLock()
        self._load()

    def _load(self):
        if self.path.exists():
            with open(self.path, 'r', encoding='utf-8') as f:
                self._data = json.load(f)
        else:
            self._data = {"keys": {}, "metadata": {}}

    def _save(self):
        with self._lock:
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, indent=2, default=str, ensure_ascii=False)

    def generate_key(self) -> str:
        return f"sk-{secrets.token_urlsafe(32)}"

    def create(self, key_data: APIKeyCreate) -> APIKeyResponse:
        with self._lock:
            key = self.generate_key()
            now = datetime.utcnow()
            entry = {
                "key": key,
                "name": key_data.name,
                "puter_token": key_data.puter_token,
                "created_at": now.isoformat(),
                "last_used": None,
                "request_count": 0,
                "is_active": True,
                "rate_limit_requests": key_data.rate_limit_requests,
                "rate_limit_tokens": key_data.rate_limit_tokens,
                "rate_limit_window_start": now.isoformat(),
            }
            self._data["keys"][key] = entry
            self._save()
            return APIKeyResponse(**entry)

    def get(self, key: str) -> Optional[APIKeyResponse]:
        entry = self._data["keys"].get(key)
        if entry:
            return APIKeyResponse(**entry)
        return None

    def update(self, key: str, update_data: APIKeyUpdate) -> Optional[APIKeyResponse]:
        with self._lock:
            if key not in self._data["keys"]:
                return None
            entry = self._data["keys"][key]
            for field, value in update_data.model_dump(exclude_unset=True).items():
                entry[field] = value
            self._save()
            return APIKeyResponse(**entry)

    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._data["keys"]:
                del self._data["keys"][key]
                self._save()
                return True
            return False

    def list_all(self) -> List[APIKeyResponse]:
        return [APIKeyResponse(**v) for v in self._data["keys"].values()]

    def _reset_window_if_needed(self, entry):
        now = datetime.utcnow()
        start_str = entry.get("rate_limit_window_start")
        if not start_str:
            entry["rate_limit_window_start"] = now.isoformat()
            return now
        try:
            start = datetime.fromisoformat(start_str)
        except ValueError:
            entry["rate_limit_window_start"] = now.isoformat()
            entry["request_count"] = 0
            return now
        if (now - start).total_seconds() >= 60:
            entry["request_count"] = 0
            entry["rate_limit_window_start"] = now.isoformat()
        return now

    def try_consume(self, key: str, limit: int):
        with self._lock:
            if key not in self._data["keys"]:
                return False
            entry = self._data["keys"][key]
            now = self._reset_window_if_needed(entry)
            if entry.get("request_count", 0) >= limit:
                self._save()
                return False
            entry["request_count"] = entry.get("request_count", 0) + 1
            entry["last_used"] = now.isoformat()
            self._save()
            return True

    def record_request(self, key: str):
        with self._lock:
            if key in self._data["keys"]:
                entry = self._data["keys"][key]
                now = self._reset_window_if_needed(entry)
                entry["request_count"] = entry.get("request_count", 0) + 1
                entry["last_used"] = now.isoformat()
                self._save()

    def get_puter_token(self, key: str) -> Optional[str]:
        entry = self._data["keys"].get(key)
        if entry and entry.get("is_active"):
            return entry.get("puter_token")
        return None

    def get_rate_limits(self, key: str) -> tuple:
        entry = self._data["keys"].get(key)
        if entry:
            return (
                entry.get("rate_limit_requests"),
                entry.get("rate_limit_tokens")
            )
        return (None, None)
