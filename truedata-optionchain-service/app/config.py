import os
from dotenv import load_dotenv

load_dotenv()

# REST API configuration
TD_API_TOKEN = os.getenv("TRUEDATA_API_TOKEN") or os.getenv("TRUEDATA_GREKS_TOKEN")
TD_API_BASE_URL = os.getenv("TRUEDATA_API_BASE_URL", "https://greeks.truedata.in/api")
# Defaults target the history host for expiries and the greeks host for option chain.
TD_EXPIRY_URL = os.getenv("TRUEDATA_EXPIRY_URL", "https://history.truedata.in/getSymbolExpiryList")
TD_OPTION_CHAIN_URL = os.getenv("TRUEDATA_OPTION_CHAIN_URL")  # optional override for option chain endpoint

CACHE_ENABLED = os.getenv("CACHE_ENABLED", "false").lower() == "true"
REDIS_URL = os.getenv("REDIS_URL")
