from io import StringIO
from datetime import datetime
import requests
import pandas as pd

from app.config import (
    TD_API_TOKEN,
    TD_API_BASE_URL,
    TD_EXPIRY_URL,
    TD_OPTION_CHAIN_URL,
)


class TDRESTClient:
    def __init__(self, token: str, base_url: str, expiry_url: str | None = None, chain_url: str | None = None):
        if not token:
            raise ValueError("TRUEDATA_API_TOKEN (or TRUEDATA_GREKS_TOKEN) is required for REST calls.")
        self.token = token
        self.base_url = base_url.rstrip("/")
        # Some endpoints live on different hosts; allow overrides and default to known paths.
        self.expiry_url = (expiry_url or "https://history.truedata.in/getSymbolExpiryList").rstrip("/")
        self.chain_url = chain_url or f"{self.base_url}/getOptionChainwithGreeks"
        self.last_expiry_response = None
        self.last_expiry_error = None
        self.last_chain_response = None
        self.last_chain_error = None

    def _headers(self):
        # TrueData REST APIs accept bearer auth via Authorization header.
        return {"Authorization": f"Bearer {self.token}"}

    def _normalize_expiry(self, expiry: str) -> str:
        """
        Normalize expiry formats. The greeks endpoint expects dd-mm-YYYY, while
        the expiry list may return YYYY-mm-dd.
        """
        if not expiry:
            return expiry
        for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(expiry, fmt).strftime("%d-%m-%Y")
            except Exception:
                continue
        return expiry

    def get_expiry_list(self, symbol: str):
        url = self.expiry_url
        # Response defaults to CSV on history host; we also include token if required.
        params = {"symbol": symbol, "response": "csv", "token": self.token}
        self.last_expiry_response = None
        self.last_expiry_error = None

        try:
            resp = requests.get(url, headers=self._headers(), params=params, timeout=15)
            self.last_expiry_response = resp.text
            resp.raise_for_status()
        except requests.HTTPError as e:
            body = resp.text if "resp" in locals() else None
            self.last_expiry_error = f"HTTPError: {e} | body={body}"
            return []
        except requests.RequestException as e:
            self.last_expiry_error = f"RequestException: {e}"
            return []

        data = None
        try:
            data = resp.json()
        except ValueError:
            pass

        # The API can return either a list or a dict containing a list.
        if isinstance(data, dict):
            for key in ("expiries", "data", "result", "expiry"):
                if key in data and isinstance(data[key], list):
                    return data[key]
        if isinstance(data, list):
            return data

        # Fallback: CSV/line-based response
        if resp.text:
            lines = [line.strip() for line in resp.text.splitlines() if line.strip()]
            if lines:
                if lines[0].lower().startswith("expiry"):
                    lines = lines[1:]
                # CSV may include comma separation; split if needed
                cleaned = []
                for line in lines:
                    parts = [p.strip() for p in line.split(",") if p.strip()]
                    cleaned.extend(parts if len(parts) > 1 else [line])
                return cleaned

        return []

    def get_option_chain_with_greeks(self, symbol: str, expiry: str, response: str = "pandas"):
        url = self.chain_url
        norm_expiry = self._normalize_expiry(expiry)
        params = {"symbol": symbol, "expiry": norm_expiry, "response": "csv", "token": self.token}
        self.last_chain_response = None
        self.last_chain_error = None

        try:
            resp = requests.get(url, headers=self._headers(), params=params, timeout=30)
            self.last_chain_response = resp.text
            resp.raise_for_status()
        except requests.HTTPError as e:
            body = resp.text if "resp" in locals() else None
            self.last_chain_error = f"HTTPError: {e} | body={body}"
            return pd.DataFrame()
        except requests.RequestException as e:
            self.last_chain_error = f"RequestException: {e}"
            return pd.DataFrame()

        if response == "pandas":
            return pd.read_csv(StringIO(resp.text))
        if response == "json":
            return resp.json()
        return resp.text


td_client = TDRESTClient(
    TD_API_TOKEN,
    TD_API_BASE_URL,
    expiry_url=TD_EXPIRY_URL,
    chain_url=TD_OPTION_CHAIN_URL,
)
