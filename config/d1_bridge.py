"""
Cloudflare D1 Database Compatibility Layer for Django.

Supports two execution modes:
1. Cloudflare Python Worker Runtime: Binds the Worker `env.DB` D1 instance and
   synchronizes schema/queries with the in-memory/ephemeral SQLite engine used by
   Django's ORM within the Worker request lifecycle.
2. Remote D1 HTTP API Mode: Allows running queries and schema exports against
   Cloudflare D1 from CLI/CI using `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_D1_DATABASE_ID`,
   and `CLOUDFLARE_API_TOKEN`.
"""
import logging
import os
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

_ACTIVE_WORKER_D1_BINDING = None


def set_worker_d1_binding(d1_binding: Any) -> None:
    """Register the Cloudflare Worker env.DB binding for the active request."""
    global _ACTIVE_WORKER_D1_BINDING
    _ACTIVE_WORKER_D1_BINDING = d1_binding


def get_worker_d1_binding() -> Any:
    """Return the active Cloudflare Worker D1 binding if running inside Workers."""
    return _ACTIVE_WORKER_D1_BINDING


class CloudflareD1RestClient:
    """HTTP Client for interacting with Cloudflare D1 REST API from management commands."""

    def __init__(
        self,
        account_id: Optional[str] = None,
        database_id: Optional[str] = None,
        api_token: Optional[str] = None,
    ) -> None:
        self.account_id = account_id or os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
        self.database_id = database_id or os.environ.get("CLOUDFLARE_D1_DATABASE_ID", "")
        self.api_token = api_token or os.environ.get("CLOUDFLARE_API_TOKEN", "")

    @property
    def is_configured(self) -> bool:
        return bool(self.account_id and self.database_id and self.api_token)

    @property
    def endpoint(self) -> str:
        return (
            f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}"
            f"/d1/database/{self.database_id}/query"
        )

    def execute_query(self, sql: str, params: Optional[List[Any]] = None) -> Dict[str, Any]:
        """Execute a parameterized SQL query against Cloudflare D1 REST API."""
        if not self.is_configured:
            raise RuntimeError(
                "Cloudflare D1 REST credentials are not configured. "
                "Set CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_D1_DATABASE_ID, and CLOUDFLARE_API_TOKEN."
            )
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {"sql": sql}
        if params:
            payload["params"] = params

        response = requests.post(self.endpoint, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        if not data.get("success", False):
            errors = data.get("errors", [])
            raise RuntimeError(f"Cloudflare D1 query error: {errors}")
        return data
