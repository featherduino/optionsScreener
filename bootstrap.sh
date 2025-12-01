#!/bin/bash

PROJECT="truedata-optionchain-service"

echo "📦 Creating project: $PROJECT"
mkdir -p $PROJECT/app/{routers,services,utils}

# -----------------------------
# requirements.txt
# -----------------------------
cat << 'EOF' > $PROJECT/requirements.txt
fastapi
uvicorn
pandas
truedata-ws
python-dotenv
redis
EOF

# -----------------------------
# .env.example
# -----------------------------
cat << 'EOF' > $PROJECT/.env.example
TRUEDATA_USERNAME=your_username
TRUEDATA_PASSWORD=your_password

CACHE_ENABLED=true
REDIS_URL=redis://localhost:6379/0
EOF

# -----------------------------
# app/__init__.py
# -----------------------------
touch $PROJECT/app/__init__.py

# -----------------------------
# app/config.py
# -----------------------------
cat << 'EOF' > $PROJECT/app/config.py
import os
from dotenv import load_dotenv

load_dotenv()

TD_USER = os.getenv("TRUEDDATA_USERNAME") or os.getenv("TRUEDATA_USERNAME")
TD_PASS = os.getenv("TRUEDDATA_PASSWORD") or os.getenv("TRUEDATA_PASSWORD")

CACHE_ENABLED = os.getenv("CACHE_ENABLED", "false").lower() == "true"
REDIS_URL = os.getenv("REDIS_URL")
EOF

# -----------------------------
# app/td_client.py
# -----------------------------
cat << 'EOF' > $PROJECT/app/td_client.py
from truedata_ws.websocket.TD import TD
from app.config import TD_USER, TD_PASS

td_client = TD(TD_USER, TD_PASS)
EOF

# -----------------------------
# app/services/expiries.py
# -----------------------------
cat << 'EOF' > $PROJECT/app/services/expiries.py
from datetime import datetime
from app.td_client import td_client

def get_expiries(symbol: str):
    try:
        return td_client.get_expiry_list(symbol)
    except:
        return []

def pick_nearest_expiry(expiries):
    if not expiries:
        return None

    today = datetime.now().date()

    parsed = []
    for e in expiries:
        try:
            d = datetime.strptime(e, "%d-%m-%Y").date()
            parsed.append((e, d))
        except:
            continue

    future = [x for x in parsed if x[1] >= today]
    pool = future if future else parsed

    pool.sort(key=lambda x: x[1])
    return pool[0][0]
EOF

# -----------------------------
# app/services/optionchain.py
# -----------------------------
cat << 'EOF' > $PROJECT/app/services/optionchain.py
from app.td_client import td_client
import pandas as pd

def fetch_chain(symbol: str, expiry: str) -> pd.DataFrame:
    try:
        df = td_client.get_option_chain_with_greeks(
            symbol=symbol,
            expiry=expiry,
            response="pandas"
        )
        return df
    except:
        return pd.DataFrame()
EOF

# -----------------------------
# app/services/analytics.py
# -----------------------------
cat << 'EOF' > $PROJECT/app/services/analytics.py
import pandas as pd

def compute_important_strikes(df: pd.DataFrame):
    if df.empty: 
        return df

    df = df.copy()

    df["score"] = (
        (df["callOI"] - df["putOI"]).abs() * 0.0001 +
        (df["callVol"] + df["putVol"]) * 0.0005 +
        (df["callltp"] - df["putltp"]).abs() * 0.05
    )

    df = df.sort_values("score", ascending=False)
    return df.head(15)
EOF

# -----------------------------
# app/routers/optionchain.py
# -----------------------------
cat << 'EOF' > $PROJECT/app/routers/optionchain.py
from fastapi import APIRouter
from app.services.expiries import get_expiries, pick_nearest_expiry
from app.services.optionchain import fetch_chain
from app.services.analytics import compute_important_strikes

router = APIRouter(prefix="/optionchain", tags=["optionchain"])

@router.get("/{symbol}")
def get_option_chain(symbol: str):
    symbol = symbol.upper()

    expiries = get_expiries(symbol)
    expiry = pick_nearest_expiry(expiries)

    if not expiry:
        return {"error": "No valid expiry", "symbol": symbol}

    df = fetch_chain(symbol, expiry)
    important = compute_important_strikes(df)

    return {
        "symbol": symbol,
        "expiry": expiry,
        "total_rows": len(df),
        "top_strikes": important.to_dict(orient="records"),
    }
EOF

# -----------------------------
# app/routers/health.py
# -----------------------------
cat << 'EOF' > $PROJECT/app/routers/health.py
from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])

@router.get("/")
def health():
    return {"status": "ok"}
EOF

# -----------------------------
# app/utils/cache.py
# -----------------------------
cat << 'EOF' > $PROJECT/app/utils/cache.py
import redis
from app.config import CACHE_ENABLED, REDIS_URL

r = None
if CACHE_ENABLED:
    r = redis.Redis.from_url(REDIS_URL)

def cache_set(key, value, ttl=30):
    if r:
        r.set(key, value, ex=ttl)

def cache_get(key):
    if r:
        return r.get(key)
    return None
EOF

# -----------------------------
# app/main.py
# -----------------------------
cat << 'EOF' > $PROJECT/app/main.py
from fastapi import FastAPI
from app.routers.optionchain import router as optionchain_router
from app.routers.health import router as health_router

app = FastAPI(title="TrueData OptionChain + Greeks API")

app.include_router(optionchain_router)
app.include_router(health_router)

@app.get("/")
def index():
    return {"msg": "TrueData OptionChain Microservice Running"}
EOF

# -----------------------------
# run.sh
# -----------------------------
cat << 'EOF' > $PROJECT/run.sh
#!/bin/bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
EOF
chmod +x $PROJECT/run.sh

# -----------------------------
# Dockerfile
# -----------------------------
cat << 'EOF' > $PROJECT/Dockerfile
FROM python:3.10

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
EOF

echo "🎉 DONE! Project created at: $PROJECT/"

