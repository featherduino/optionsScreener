import pandas as pd

def compute_important_strikes(df: pd.DataFrame):
    if df.empty: 
        return df

    df = df.copy()

    required = {
        "callOI": "callOI",
        "putOI": "putOI",
        "callVol": "callVol",
        "putVol": "putVol",
        "callltp": "callltp",
        "putltp": "putltp",
    }

    # Normalize column names to lower for matching against pandas columns
    cols_lower = {c.lower(): c for c in df.columns}

    missing = []
    resolved = {}
    for needed_lower, needed_original in required.items():
        if needed_lower in cols_lower:
            resolved[needed_original] = cols_lower[needed_lower]
        else:
            missing.append(needed_lower)

    # If we are missing key columns, just return the df as-is to avoid 500s.
    if missing:
        return df

    df["score"] = (
        (df[resolved["callOI"]] - df[resolved["putOI"]]).abs() * 0.0001 +
        (df[resolved["callVol"]] + df[resolved["putVol"]]) * 0.0005 +
        (df[resolved["callltp"]] - df[resolved["putltp"]]).abs() * 0.05
    )

    df = df.sort_values("score", ascending=False)
    return df.head(15)


def build_chart_views(df: pd.DataFrame):
    """
    Prepare chart-friendly slices:
    - OI bars: strike, call OI, put OI
    - IV skew: strike, call IV, put IV
    - PCR heatmap: strike, pcr
    """
    if df.empty:
        return {"oi_bars": [], "iv_skew": [], "pcr_heatmap": []}

    work = df.copy()
    work.columns = [c.lower() for c in work.columns]

    def pick(*options):
        for opt in options:
            if opt in work.columns:
                return opt
        return None

    # Try multiple variants for each field
    strike_col = pick("strike", "strikeprice")
    call_oi_col = pick("calloi", "call_oi", "coi", "callopeninterest")
    put_oi_col = pick("putoi", "put_oi", "poi", "putopeninterest")
    call_iv_col = pick("calliv", "civ", "call_iv", "ivcall")
    put_iv_col = pick("putiv", "piv", "put_iv", "ivput")
    call_ltp_col = pick("callltp", "call_ltp", "ltpcall", "ltpce")
    put_ltp_col = pick("putltp", "put_ltp", "ltpput", "ltppe")
    call_bid_col = pick("callbid", "bidcall", "call_bid", "bidce")
    put_bid_col = pick("putbid", "bidput", "put_bid", "bidpe")
    call_ask_col = pick("callask", "askcall", "call_ask", "askce", "calloffer")
    put_ask_col = pick("putask", "askput", "put_ask", "askpe", "putoffer")

    charts = {"oi_bars": [], "iv_skew": [], "pcr_heatmap": []}
    charts["pcr_total"] = None
    charts["prices"] = []

    # OI bars
    if strike_col and call_oi_col and put_oi_col:
        oi = work[[strike_col, call_oi_col, put_oi_col]].copy()
        oi.columns = ["strike", "calloi", "putoi"]
        charts["oi_bars"] = _to_safe_records(oi)

    # IV skew
    if strike_col and call_iv_col and put_iv_col:
        iv = work[[strike_col, call_iv_col, put_iv_col]].copy()
        iv.columns = ["strike", "calliv", "putiv"]
        charts["iv_skew"] = _to_safe_records(iv)

    # PCR heatmap: per-strike put OI / call OI, safe division
    if strike_col and call_oi_col and put_oi_col:
        pcr_df = work[[strike_col, call_oi_col, put_oi_col]].copy()
        pcr_df[call_oi_col] = pd.to_numeric(pcr_df[call_oi_col], errors="coerce")
        pcr_df[put_oi_col] = pd.to_numeric(pcr_df[put_oi_col], errors="coerce")
        with pd.option_context("mode.use_inf_as_na", True):
            pcr_df["pcr"] = pcr_df[put_oi_col] / pcr_df[call_oi_col]
        pcr_df.columns = ["strike", call_oi_col, put_oi_col, "pcr"]
        charts["pcr_heatmap"] = _to_safe_records(pcr_df[["strike", "pcr"]])
        # Aggregate PCR = total_put_oi / total_call_oi
        total_call = pcr_df[call_oi_col].sum(skipna=True)
        total_put = pcr_df[put_oi_col].sum(skipna=True)
        charts["pcr_total"] = (total_put / total_call) if total_call and total_call != 0 else None

    # Prices (LTP and bid/ask)
    price_cols = [c for c in [call_ltp_col, put_ltp_col, call_bid_col, put_bid_col, call_ask_col, put_ask_col] if c]
    if strike_col and price_cols:
        price_df = work[[strike_col] + price_cols].copy()
        rename_map = {}
        if call_ltp_col:
            rename_map[call_ltp_col] = "callltp"
        if put_ltp_col:
            rename_map[put_ltp_col] = "putltp"
        if call_bid_col:
            rename_map[call_bid_col] = "callbid"
        if put_bid_col:
            rename_map[put_bid_col] = "putbid"
        if call_ask_col:
            rename_map[call_ask_col] = "callask"
        if put_ask_col:
            rename_map[put_ask_col] = "putask"
        price_df = price_df.rename(columns=rename_map)
        price_df = price_df.rename(columns={strike_col: "strike"})
        charts["prices"] = _to_safe_records(price_df)

    return charts


def _to_safe_records(df: pd.DataFrame):
    """Convert DataFrame to JSON-safe records with None for NaN/inf."""
    safe_df = df.replace([float("inf"), float("-inf")], pd.NA)
    safe_df = safe_df.where(pd.notnull(safe_df), None)
    return safe_df.to_dict(orient="records")
