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

    charts = {"oi_bars": [], "iv_skew": [], "pcr_heatmap": []}

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

    # PCR heatmap
    if strike_col and call_oi_col and put_oi_col:
        pcr_df = work[[strike_col, call_oi_col, put_oi_col]].copy()
        pcr_df[call_oi_col] = pd.to_numeric(pcr_df[call_oi_col], errors="coerce")
        pcr_df[put_oi_col] = pd.to_numeric(pcr_df[put_oi_col], errors="coerce")
        pcr_df["pcr"] = pcr_df[put_oi_col] / pcr_df[call_oi_col]
        pcr_df.columns = ["strike", call_oi_col, put_oi_col, "pcr"]
        charts["pcr_heatmap"] = _to_safe_records(pcr_df[["strike", "pcr"]])

    return charts


def _to_safe_records(df: pd.DataFrame):
    """Convert DataFrame to JSON-safe records with None for NaN/inf."""
    safe_df = df.replace([float("inf"), float("-inf")], pd.NA)
    safe_df = safe_df.where(pd.notnull(safe_df), None)
    return safe_df.to_dict(orient="records")
