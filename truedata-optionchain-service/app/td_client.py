from io import StringIO
from datetime import datetime
import time
import requests
import pandas as pd

from app.config import (
    TD_API_TOKEN,
    TD_USERNAME,
    TD_PASSWORD,
    TD_AUTH_URL,
    TD_API_BASE_URL,
    TD_EXPIRY_URL,
    TD_OPTION_CHAIN_URL,
)


class TDRESTClient:
    def __init__(
        self,
        token: str | None,
        base_url: str,
        expiry_url: str | None = None,
        chain_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        auth_url: str | None = None,
    ):
        if not token and not (username and password):
            raise ValueError("Provide TRUEDATA_API_TOKEN or TRUEDATA_USERNAME/TRUEDATA_PASSWORD for REST calls.")
        self.static_token = token  # fallback if we cannot fetch
        self.username = username
        self.password = password
        self.auth_url = (auth_url or "https://auth.truedata.in/token").rstrip("/")
        self.base_url = base_url.rstrip("/")
        # Some endpoints live on different hosts; allow overrides and default to known paths.
        self.expiry_url = (expiry_url or "https://history.truedata.in/getSymbolExpiryList").rstrip("/")
        self.chain_url = chain_url or f"{self.base_url}/getOptionChainwithGreeks"
        self.last_expiry_response = None
        self.last_expiry_error = None
        self.last_chain_response = None
        self.last_chain_error = None
        self._access_token = token
        self._token_expiry_ts = 0.0
        self._token_last_refresh_ts = 0.0
        self._token_source = "static" if token else None

    def _fetch_token(self):
        if not (self.username and self.password):
            # If no credentials, stick with static token.
            return
        try:
            resp = requests.post(
                self.auth_url,
                data={"username": self.username, "password": self.password, "grant_type": "password"},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=15,
            )
            resp.raise_for_status()
            payload = resp.json()
            token = payload.get("access_token")
            ttl = float(payload.get("expires_in", 0)) or 0.0
            if token:
                self._access_token = token
                # Buffer 60s before expiry
                self._token_expiry_ts = time.time() + max(ttl - 60, 60)
        except Exception:
            # Leave existing token in place; caller will handle failure
            pass
        else:
            if token:
                self._token_source = "login"
                self._token_last_refresh_ts = time.time()

    def _ensure_token(self):
        now = time.time()
        if self._access_token and now < self._token_expiry_ts:
            return
        if not self._access_token and self.static_token:
            # Use static token initially
            self._access_token = self.static_token
            self._token_expiry_ts = now + 3600
            self._token_source = "static"
            return
        self._fetch_token()

    def _headers(self):
        self._ensure_token()
        return {"Authorization": f"Bearer {self._access_token}"} if self._access_token else {}

    def token_status(self):
        now = time.time()
        seconds_left = (self._token_expiry_ts - now) if self._token_expiry_ts else None
        expires_at = (
            datetime.utcfromtimestamp(self._token_expiry_ts).isoformat() + "Z"
            if self._token_expiry_ts
            else None
        )
        last_refresh = (
            datetime.utcfromtimestamp(self._token_last_refresh_ts).isoformat() + "Z"
            if self._token_last_refresh_ts
            else None
        )
        return {
            "has_token": bool(self._access_token),
            "source": self._token_source,
            "expires_at": expires_at,
            "seconds_left": seconds_left,
            "last_refresh": last_refresh,
            "last_expiry_error": self.last_expiry_error,
            "last_chain_error": self.last_chain_error,
        }

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
            resp_obj = resp if "resp" in locals() else None
            if resp_obj is not None and resp_obj.status_code == 401:
                self._fetch_token()
                try:
                    resp_retry = requests.get(url, headers=self._headers(), params=params, timeout=15)
                    self.last_expiry_response = resp_retry.text
                    resp_retry.raise_for_status()
                    resp_obj = resp_retry
                except Exception:
                    resp_obj = resp_retry if "resp_retry" in locals() else None
            if resp_obj is not None and resp_obj.status_code == 401:
                self.last_expiry_error = "Unauthorized (401) after token refresh"
                return []
            body = resp_obj.text if resp_obj is not None else None
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
            resp_obj = resp if "resp" in locals() else None
            if resp_obj is not None and resp_obj.status_code == 401:
                # Try once with a fresh token
                self._fetch_token()
                try:
                    resp_retry = requests.get(url, headers=self._headers(), params=params, timeout=30)
                    self.last_chain_response = resp_retry.text
                    resp_retry.raise_for_status()
                    resp_obj = resp_retry
                except Exception:
                    resp_obj = resp_retry if "resp_retry" in locals() else None
            if resp_obj is not None and resp_obj.status_code == 401:
                self.last_chain_error = "Unauthorized (401) after token refresh"
                return pd.DataFrame()
            body = resp_obj.text if resp_obj is not None else None
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
    username=TD_USERNAME,
    password=TD_PASSWORD,
    auth_url=TD_AUTH_URL,
)
