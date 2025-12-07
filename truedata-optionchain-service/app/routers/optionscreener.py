"""Proxy endpoints for the external Option Screener API."""

from __future__ import annotations

import base64
import io
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from app.services.charts import (
    render_heatmap_chart,
    render_rsi_trend_chart,
    render_top_movers_chart,
)
from app.services.drive import DriveConfigurationError, DriveUploadError, upload_png
from app.services.optionscreener import (
    ScreenerConfigurationError,
    ScreenerServiceError,
    fetch_screener_json,
)


router = APIRouter(prefix="/optionscreener", tags=["option-screener"])


def _fetch_json(path: str, params: dict[str, Any] | None = None):
    try:
        return fetch_screener_json(path, params)
    except ScreenerConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ScreenerServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/overview")
def overview(date: str | None = None):
    return _fetch_json("/overview", {"date": date})


@router.get("/heatmap")
def heatmap(date: str | None = None):
    return _fetch_json("/heatmap", {"date": date})


@router.get("/top-symbols")
def top_symbols(date: str | None = None):
    return _fetch_json("/top-symbols", {"date": date})


@router.get("/quote")
def quote(symbol: str | None = None):
    return _fetch_json("/quote", {"symbol": symbol})


@router.get("/charts/heatmap")
def heatmap_chart(date: str | None = None, format: str = "png", upload: str | None = None):
    data = _fetch_json("/heatmap", {"date": date})
    payload = render_heatmap_chart(data or [])
    return _chart_response("heatmap", payload, format, upload)


@router.get("/charts/top-movers")
def top_movers_chart(date: str | None = None, format: str = "png", upload: str | None = None):
    data = _fetch_json("/top-symbols", {"date": date})
    payload = render_top_movers_chart(data or [])
    return _chart_response("top-movers", payload, format, upload)


@router.get("/charts/rsi-trend")
def rsi_trend_chart(date: str | None = None, format: str = "png", upload: str | None = None):
    data = _fetch_json("/heatmap", {"date": date})
    payload = render_rsi_trend_chart(data or [])
    return _chart_response("rsi-trend", payload, format, upload)


def _chart_response(kind: str, payload: bytes, format: str, upload: str | None):
    if upload == "drive":
        filename = f"{kind}.png"
        try:
            result = upload_png(filename, payload)
            return JSONResponse(result)
        except DriveConfigurationError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        except DriveUploadError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    if format == "html":
        encoded = base64.b64encode(payload).decode("ascii")
        html = f"<img alt='{kind}' src='data:image/png;base64,{encoded}' />"
        return HTMLResponse(content=html)

    return StreamingResponse(io.BytesIO(payload), media_type="image/png")


@router.get("/optionsScanner")
def options_scanner(request: Request):
    params = dict(request.query_params)
    return _fetch_json("/optionsScanner", params)
