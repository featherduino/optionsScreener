"""Utilities to render Option Screener chart PNGs."""

from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.ticker import FormatStrFormatter
import pandas as pd
import seaborn as sns
from PIL import Image


def _finalize(fig) -> bytes:
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=160)
    plt.close(fig)
    buf.seek(0)
    raw = buf.read()

    # Ensure Instagram-friendly aspect ratio by centering chart on 1080x1350 canvas.
    try:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        canvas_size = (1080, 1350)  # 4:5 aspect ratio
        img.preview_size = canvas_size
        img.thumbnail(canvas_size, Image.LANCZOS)
        canvas = Image.new("RGB", canvas_size, color="white")
        offset = ((canvas_size[0] - img.width) // 2, (canvas_size[1] - img.height) // 2)
        canvas.paste(img, offset)
        out = io.BytesIO()
        canvas.save(out, format="PNG")
        out.seek(0)
        return out.read()
    except Exception:
        return raw


def render_heatmap_chart(rows):
    df = pd.DataFrame(rows)
    if df.empty:
        fig, ax = plt.subplots(figsize=(6, 2))
        ax.text(0.5, 0.5, "No heatmap data", ha="center", va="center")
        ax.axis("off")
        return _finalize(fig)

    df = df.copy()
    idx = _pick_col(df, ["sector_norm", "sector", "name"])
    metrics = [c for c in ["score", "rsi", "change_pct", "volspike"] if c in df.columns]
    if not idx or not metrics:
        fig, ax = plt.subplots(figsize=(6, 2))
        ax.text(0.5, 0.5, "Missing heatmap columns", ha="center", va="center")
        ax.axis("off")
        return _finalize(fig)

    chart_df = df.set_index(idx)[metrics]
    for col in chart_df.columns:
        chart_df[col] = pd.to_numeric(chart_df[col], errors="coerce")
    chart_df = chart_df.fillna(0)
    fig, ax = plt.subplots(figsize=(1.5 * len(metrics), 0.4 * len(chart_df) + 1))
    sns.heatmap(chart_df, annot=True, fmt=".2f", cmap="RdYlGn", ax=ax, cbar=True)
    ax.set_title("Sector Heatmap")
    return _finalize(fig)


def render_top_movers_chart(rows):
    df = pd.DataFrame(rows)
    if df.empty:
        fig, ax = plt.subplots(figsize=(6, 2))
        ax.text(0.5, 0.5, "No top symbols", ha="center", va="center")
        ax.axis("off")
        return _finalize(fig)

    df = df.copy()
    symbol_col = _pick_col(df, ["symbol", "ticker"]) or df.columns[0]
    score_col = _pick_col(df, ["score", "rank", "value"]) or df.columns[1]
    chart_df = df[[symbol_col, score_col]].copy()
    chart_df[score_col] = pd.to_numeric(chart_df[score_col], errors="coerce")
    chart_df = chart_df.dropna(subset=[score_col])
    chart_df = chart_df.nlargest(10, score_col)
    chart_df = chart_df.sort_values(score_col)

    fig, ax = plt.subplots(figsize=(8, 4))
    sns.barplot(data=chart_df, x=score_col, y=symbol_col, palette="Blues_r", ax=ax)
    ax.set_title("Top Symbols")
    ax.set_xlabel(score_col)
    ax.set_ylabel("Symbol")
    ax.xaxis.set_major_formatter(FormatStrFormatter("%.1f"))
    for container in ax.containers:
        ax.bar_label(container, fmt="%.1f", padding=2)
    return _finalize(fig)


def render_rsi_trend_chart(rows):
    df = pd.DataFrame(rows)
    if df.empty:
        fig, ax = plt.subplots(figsize=(6, 2))
        ax.text(0.5, 0.5, "No RSI data", ha="center", va="center")
        ax.axis("off")
        return _finalize(fig)

    df = df.copy()
    sector_col = _pick_col(df, ["sector_norm", "sector", "name"]) or df.columns[0]
    rsi_col = _pick_col(df, ["rsi"])
    if not rsi_col:
        fig, ax = plt.subplots(figsize=(6, 2))
        ax.text(0.5, 0.5, "RSI column missing", ha="center", va="center")
        ax.axis("off")
        return _finalize(fig)

    chart_df = df[[sector_col, rsi_col]].copy()
    chart_df[rsi_col] = pd.to_numeric(chart_df[rsi_col], errors="coerce").round(1)
    chart_df = chart_df.dropna()
    chart_df = chart_df.sort_values(rsi_col, ascending=False)

    fig, ax = plt.subplots(figsize=(9, max(4, 0.35 * len(chart_df) + 1)))
    sns.lineplot(data=chart_df, x=rsi_col, y=sector_col, marker="o", ax=ax)
    ax.set_title("Sector RSI")
    ax.set_xlabel("RSI")
    ax.set_ylabel("Sector")
    ax.xaxis.set_major_formatter(FormatStrFormatter("%.1f"))
    ax.grid(axis="x", linestyle="--", alpha=0.3)
    return _finalize(fig)


def _pick_col(df: pd.DataFrame, candidates):
    cols = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in cols:
            return cols[cand.lower()]
    return None
