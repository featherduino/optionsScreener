#!/usr/bin/env bash
set -euo pipefail

# Start FastAPI backend on 8000
uvicorn app.main:app --host 0.0.0.0 --port 8000 &

# Start Streamlit on 8501
exec streamlit run streamlit_dashboard.py \
  --server.port 8501 \
  --server.address 0.0.0.0 \
  --browser.gatherUsageStats false
