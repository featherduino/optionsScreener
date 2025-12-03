import os
import requests
import pandas as pd
import plotly.express as px
import streamlit as st


API_BASE = os.getenv("OPTIONCHAIN_API", "http://localhost:8000")


def fetch_optionchain(symbol: str, expiry: str | None = None):
    url = f"{API_BASE}/optionchain/{symbol}"
    params = {}
    if expiry:
        params["expiry"] = expiry
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def inject_ga():
    measurement_id = os.getenv("GA_MEASUREMENT_ID")
    if not measurement_id:
        return
    ga_snippet = f"""
    <!-- Google tag (gtag.js) -->
    <script async src="https://www.googletagmanager.com/gtag/js?id={measurement_id}"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){{dataLayer.push(arguments);}}
      gtag('js', new Date());
      gtag('config', '{measurement_id}');
    </script>
    """
    st.markdown(ga_snippet, unsafe_allow_html=True)


def compute_alerts(charts: dict):
    alerts = []
    # Prefer aggregate PCR (total put OI / total call OI), fallback to mean of per-strike PCRs.
    aggregate_pcr = charts.get("pcr_total")
    # PCR shift alert
    pcr_df = pd.DataFrame(charts.get("pcr_heatmap") or [])
    if aggregate_pcr is not None:
        curr_mean = pd.to_numeric(pd.Series([aggregate_pcr]), errors="coerce").mean()
    elif not pcr_df.empty and "pcr" in pcr_df.columns:
        curr_mean = pd.to_numeric(pcr_df["pcr"], errors="coerce").mean()
    else:
        curr_mean = None

    if curr_mean is not None and pd.notnull(curr_mean):
        prev_mean = st.session_state.get("prev_pcr_mean")
        if prev_mean is not None and pd.notnull(prev_mean):
            delta = curr_mean - prev_mean
            if abs(delta) > 0.2:
                alerts.append(f"PCR shifted by {delta:+.2f} (prev {prev_mean:.2f} → now {curr_mean:.2f})")
        if pd.notnull(curr_mean):
            st.session_state["prev_pcr_mean"] = curr_mean

    # IV spike alert
    iv_df = pd.DataFrame(charts.get("iv_skew") or [])
    if not iv_df.empty:
        iv_cols = [c for c in ["calliv", "putiv"] if c in iv_df.columns]
        if iv_cols:
            curr_iv = pd.to_numeric(iv_df[iv_cols].stack(), errors="coerce").mean()
            prev_iv = st.session_state.get("prev_iv_mean")
            if prev_iv is not None and pd.notnull(curr_iv) and prev_iv > 0:
                spike = (curr_iv - prev_iv) / prev_iv
                if spike > 0.10:
                    alerts.append(f"IV up {spike*100:.1f}% (prev {prev_iv:.2f} → now {curr_iv:.2f})")
            if pd.notnull(curr_iv):
                st.session_state["prev_iv_mean"] = curr_iv

    return alerts


def generate_trade_idea(charts: dict):
    oi_df = pd.DataFrame(charts.get("oi_bars") or [])
    pcr_df = pd.DataFrame(charts.get("pcr_heatmap") or [])
    iv_df = pd.DataFrame(charts.get("iv_skew") or [])

    if oi_df.empty:
        return None

    # Normalize numerics
    oi_df["calloi"] = pd.to_numeric(oi_df.get("calloi"), errors="coerce")
    oi_df["putoi"] = pd.to_numeric(oi_df.get("putoi"), errors="coerce")

    bias = "neutral"
    pcr_mean = None
    if not pcr_df.empty and "pcr" in pcr_df.columns:
        pcr_mean = pd.to_numeric(pcr_df["pcr"], errors="coerce").mean()
        if pd.notnull(pcr_mean):
            if pcr_mean > 1.1:
                bias = "bullish"
            elif pcr_mean < 0.9:
                bias = "bearish"

    iv_mean = None
    if not iv_df.empty:
        iv_cols = [c for c in ["calliv", "putiv"] if c in iv_df.columns]
        if iv_cols:
            iv_mean = pd.to_numeric(iv_df[iv_cols].stack(), errors="coerce").mean()

    # Identify OI walls
    top_call = oi_df.sort_values("calloi", ascending=False).head(1)
    top_put = oi_df.sort_values("putoi", ascending=False).head(1)
    if top_call.empty or top_put.empty:
        return None
    call_strike = top_call.iloc[0]["strike"]
    put_strike = top_put.iloc[0]["strike"]

    # Pick strategy
    idea = []
    iv_note = ""
    if iv_mean and pd.notnull(iv_mean):
        if iv_mean > 0.35:
            iv_note = f"IV high ({iv_mean:.2f}) → favor credit spreads."
        elif iv_mean < 0.20:
            iv_note = f"IV low ({iv_mean:.2f}) → favor debit spreads."

    if bias == "bullish":
        idea.append(f"Bias: bullish (PCR ~ {pcr_mean:.2f}). Sell put credit spread near put wall {put_strike}, hedge lower.")
    elif bias == "bearish":
        idea.append(f"Bias: bearish (PCR ~ {pcr_mean:.2f}). Sell call credit spread near call wall {call_strike}, hedge higher.")
    else:
        idea.append("Bias: neutral. Consider iron condor around put wall {0} and call wall {1}.".format(put_strike, call_strike))

    if iv_note:
        idea.append(iv_note)

    return " ".join(idea)


def generate_signals(charts: dict):
    """
    Produce human-readable signals using OI walls, PCR bias, and IV level.
    """
    signals = []

    oi_df = pd.DataFrame(charts.get("oi_bars") or [])
    pcr_df = pd.DataFrame(charts.get("pcr_heatmap") or [])
    iv_df = pd.DataFrame(charts.get("iv_skew") or [])

    if not oi_df.empty:
        oi_df["calloi"] = pd.to_numeric(oi_df.get("calloi"), errors="coerce")
        oi_df["putoi"] = pd.to_numeric(oi_df.get("putoi"), errors="coerce")
        top_calls = oi_df.sort_values("calloi", ascending=False).head(2)
        top_puts = oi_df.sort_values("putoi", ascending=False).head(2)
        if not top_calls.empty:
            signals.append(f"Max Call OI (resistance): {', '.join(top_calls['strike'].astype(str).tolist())}")
        if not top_puts.empty:
            signals.append(f"Max Put OI (support): {', '.join(top_puts['strike'].astype(str).tolist())}")

    pcr_mean = None
    aggregate_pcr = charts.get("pcr_total")
    if aggregate_pcr is not None:
        pcr_mean = pd.to_numeric(pd.Series([aggregate_pcr]), errors="coerce").mean()
    elif not pcr_df.empty and "pcr" in pcr_df.columns:
        pcr_mean = pd.to_numeric(pcr_df["pcr"], errors="coerce").mean()
    if pcr_mean is not None and pd.notnull(pcr_mean):
        bias = "neutral"
        if pcr_mean > 1.1:
            bias = "bullish"
        elif pcr_mean < 0.9:
            bias = "bearish"
        signals.append(f"PCR ≈ {pcr_mean:.2f} ({bias})")

    iv_mean = None
    if not iv_df.empty:
        iv_cols = [c for c in ["calliv", "putiv"] if c in iv_df.columns]
        if iv_cols:
            iv_mean = pd.to_numeric(iv_df[iv_cols].stack(), errors="coerce").mean()
            if pd.notnull(iv_mean):
                signals.append(f"Avg IV ≈ {iv_mean:.2f}")

    return signals


def main():
    st.set_page_config(page_title="OptionChain Analytics", layout="wide")
    inject_ga()
    st.title("OptionChain Analytics")

    # Manual refresh button to avoid unnecessary polling
    st.button("Refresh data")

    symbol = st.text_input("Symbol", value="RELIANCE").strip().upper()
    expiry_input = st.text_input("Expiry (optional, e.g., 30-12-2025)", value="").strip()
    if not symbol:
        st.stop()

    try:
        data = fetch_optionchain(symbol, expiry_input or None)
    except Exception as e:
        st.error(f"Failed to fetch data: {e}")
        st.stop()

    if data.get("error"):
        st.error(f"Backend error: {data.get('error')}")
        hints = []
        if data.get("expiry_error"):
            hints.append(f"Expiry lookup failed: {data['expiry_error']}")
        if data.get("chain_error"):
            hints.append(f"Option chain fetch failed: {data['chain_error']}")
        if not hints:
            hints.append("Verify TRUEDATA credentials/tokens and API host configuration.")
        for h in hints:
            st.info(h)
        if data.get("expiry_candidates"):
            st.write("Expiry candidates returned:", data["expiry_candidates"])
        if data.get("requested_expiry"):
            st.write("Requested expiry:", data["requested_expiry"])
        st.stop()

    if data.get("total_rows", 0) == 0:
        st.warning("No option chain rows returned. Check that your TrueData credentials are valid and the symbol has an active expiry.")
        st.info(f"Expiry used: {data.get('expiry')}")
        err = data.get("chain_error")
        resp = data.get("chain_response")
        if err or resp:
            with st.expander("Debug details from backend"):
                if err:
                    st.write("Chain error:", err)
                if resp:
                    snippet = resp if len(resp) < 800 else (resp[:800] + " …")
                    st.code(snippet or "(empty response)", language="text")
        st.stop()

    st.write(f"Expiry: {data.get('expiry')}")
    charts = data.get("charts") or {}

    alerts = compute_alerts(charts)
    if alerts:
        for a in alerts:
            st.warning(a)

    st.markdown("### Signals")
    sigs = generate_signals(charts)
    if sigs:
        for s in sigs:
            st.info(s)
    else:
        st.info("No signals available.")

    # Open Interest Bars
    oi_df = pd.DataFrame(charts.get("oi_bars") or [])
    if not oi_df.empty:
        fig_oi = px.bar(
            oi_df,
            x="strike",
            y=["calloi", "putoi"],
            barmode="group",
            labels={"value": "Open Interest", "strike": "Strike"},
            title="Open Interest (CE vs PE)",
            color_discrete_map={"calloi": "#1f77b4", "putoi": "#2ca02c"},
        )
        st.plotly_chart(fig_oi, use_container_width=True)
    else:
        st.info("No OI data available.")

    # LTP / Bid-Ask table
    price_df = pd.DataFrame(charts.get("prices") or [])
    if not price_df.empty:
        price_df = price_df.sort_values("strike")
        price_df = price_df.rename(
            columns={
                "callltp": "Call LTP",
                "putltp": "Put LTP",
                "callbid": "Call Bid",
                "putbid": "Put Bid",
                "callask": "Call Ask",
                "putask": "Put Ask",
                "strike": "Strike",
            }
        )
        st.markdown("### LTP & Bid/Ask by Strike")
        st.dataframe(price_df, use_container_width=True)
    else:
        st.info("No LTP / bid-ask data available.")

    # IV Skew
    iv_df = pd.DataFrame(charts.get("iv_skew") or [])
    if not iv_df.empty:
        fig_iv = px.line(
            iv_df.sort_values("strike"),
            x="strike",
            y=["calliv", "putiv"],
            labels={"value": "IV", "strike": "Strike"},
            title="IV Skew",
            color_discrete_map={"calliv": "#1f77b4", "putiv": "#2ca02c"},
        )
        st.plotly_chart(fig_iv, use_container_width=True)
    else:
        st.info("No IV data available.")

    # PCR Heatmap
    pcr_df = pd.DataFrame(charts.get("pcr_heatmap") or [])
    if not pcr_df.empty:
        pcr_df = pcr_df.dropna(subset=["pcr"])
        fig_pcr = px.bar(
            pcr_df.sort_values("strike"),
            x="strike",
            y="pcr",
            color="pcr",
            color_continuous_scale=["red", "orange", "green"],
            labels={"pcr": "PCR", "strike": "Strike"},
            title="PCR by Strike",
        )
        st.plotly_chart(fig_pcr, use_container_width=True)
    else:
        st.info("No PCR data available.")

    if charts.get("pcr_total") is not None:
        st.markdown(f"**Aggregate PCR (total put OI / total call OI):** {charts['pcr_total']:.2f}")

    st.markdown("### Quick Idea (heuristic)")
    idea = generate_trade_idea(charts)
    if idea:
        st.success(idea)
    else:
        st.info("Insufficient data to suggest an idea.")

    st.markdown("### Historical OI Trends")
    hist = data.get("history") or []
    hist_df = pd.DataFrame(hist)
    if not hist_df.empty and {"timestamp", "calloi", "putoi"} <= set(hist_df.columns):
        hist_df["timestamp"] = pd.to_datetime(hist_df["timestamp"])
        hist_df = hist_df.sort_values("timestamp")
        fig_hist = px.line(
            hist_df,
            x="timestamp",
            y=["calloi", "putoi"],
            labels={"value": "Open Interest", "timestamp": "Time"},
            title="Historical OI (latest snapshots)",
            color_discrete_map={"calloi": "#1f77b4", "putoi": "#2ca02c"},
        )
        st.plotly_chart(fig_hist, use_container_width=True)

        # OI change chart (delta between snapshots)
        delta_df = hist_df[["timestamp", "calloi", "putoi"]].copy()
        delta_df["call_delta"] = delta_df["calloi"].diff()
        delta_df["put_delta"] = delta_df["putoi"].diff()
        fig_delta = px.bar(
            delta_df,
            x="timestamp",
            y=["call_delta", "put_delta"],
            labels={"value": "Δ Open Interest", "timestamp": "Time"},
            title="Change in OI (per snapshot)",
            barmode="group",
            color_discrete_map={"call_delta": "#1f77b4", "put_delta": "#2ca02c"},
        )
        st.plotly_chart(fig_delta, use_container_width=True)
    else:
        st.info("No historical OI data available (enable Redis caching to persist snapshots).")


if __name__ == "__main__":
    main()
