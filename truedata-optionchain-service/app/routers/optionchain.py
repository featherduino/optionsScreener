from fastapi import APIRouter
import pandas as pd
import numpy as np
import math
import json
from datetime import datetime

from app.services.expiries import get_expiries, pick_nearest_expiry
from app.services.optionchain import fetch_chain
from app.services.analytics import compute_important_strikes, build_chart_views
from app.td_client import td_client
from app.utils.cache import r

router = APIRouter(prefix="/optionchain", tags=["optionchain"])

# --- Helper: Clean all NaN / inf values recursively ---
def clean_json_safe(obj):
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, (np.floating, np.integer)):
        val = obj.item()
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            return None
        return val
    if isinstance(obj, dict):
        return {k: clean_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_json_safe(i) for i in obj]
    return obj


@router.get("/{symbol}")
def get_option_chain(symbol: str):
    symbol = symbol.upper()

    # 1️⃣ Get nearest expiry
    expiries = get_expiries(symbol)
    expiry = pick_nearest_expiry(expiries)

    if not expiry:
        return {
            "error": "No valid expiry",
            "symbol": symbol,
            "expiry_response": getattr(td_client, "last_expiry_response", None),
            "expiry_error": getattr(td_client, "last_expiry_error", None),
        }

    # 2️⃣ Fetch option chain
    df = fetch_chain(symbol, expiry)
    if df.empty:
        return {
            "symbol": symbol,
            "expiry": expiry,
            "total_rows": 0,
            "top_strikes": [],
            "chain_response": getattr(td_client, "last_chain_response", None),
            "chain_error": getattr(td_client, "last_chain_error", None),
        }

    # 3️⃣ Compute important strikes
    important = compute_important_strikes(df)
    charts = build_chart_views(df)
    history = record_and_fetch_history(symbol, expiry, df)

    # 4️⃣ Replace NaN / inf inside DataFrame
    important = important.replace([float("inf"), float("-inf")], pd.NA)
    important = important.where(pd.notnull(important), None)

    # 5️⃣ Build payload and clean recursively
    payload = {
        "symbol": symbol,
        "expiry": expiry,
        "total_rows": len(df),
        "top_strikes": important.to_dict(orient="records"),
        "charts": charts,
        "history": history,
    }

    return clean_json_safe(payload)


def record_and_fetch_history(symbol: str, expiry: str, df: pd.DataFrame):
    """Persist a simple OI snapshot (total call/put OI) for trend plotting."""
    if r is None or df.empty:
        return []

    try:
        work = df.copy()
        work.columns = [c.lower() for c in work.columns]
        call_oi = pd.to_numeric(work.get("calloi"), errors="coerce").sum()
        put_oi = pd.to_numeric(work.get("putoi"), errors="coerce").sum()
    except Exception:
        return []

    snapshot = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "calloi": float(call_oi) if pd.notnull(call_oi) else None,
        "putoi": float(put_oi) if pd.notnull(put_oi) else None,
        "expiry": expiry,
    }

    key = f"oi_history:{symbol}:{expiry}"
    try:
        r.lpush(key, json.dumps(snapshot))
        r.ltrim(key, 0, 30)  # keep latest 31 entries
        r.expire(key, 60 * 60 * 24 * 10)  # 10 days
        raw = r.lrange(key, 0, -1) or []
        out = []
        for entry in raw:
            try:
                out.append(json.loads(entry))
            except Exception:
                continue
        return out[::-1]  # oldest first
    except Exception:
        return []
