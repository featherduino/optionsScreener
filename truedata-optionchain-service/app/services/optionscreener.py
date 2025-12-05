"""Helpers for proxying the external Option Screener API."""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import requests

from app.config import OPTION_SCREENER_BASE_URL


class ScreenerConfigurationError(RuntimeError):
    """Raised when the screener base URL is missing."""


class ScreenerServiceError(RuntimeError):
    """Raised when the downstream screener API returns an error."""


def _build_url(path: str) -> str:
    base = (OPTION_SCREENER_BASE_URL or "").rstrip("/")
    if not base:
        raise ScreenerConfigurationError("OPTION_SCREENER_BASE_URL is not configured")
    path = path if path.startswith("/") else f"/{path}"
    return urljoin(base + "/", path.lstrip("/"))


def fetch_screener_json(path: str, params: dict[str, Any] | None = None) -> Any:
    url = _build_url(path)
    try:
        resp = requests.get(url, params=_clean_params(params), timeout=20)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        raise ScreenerServiceError(str(exc)) from exc


def _clean_params(params: dict[str, Any] | None) -> dict[str, Any] | None:
    if not params:
        return None
    return {k: v for k, v in params.items() if v is not None}
