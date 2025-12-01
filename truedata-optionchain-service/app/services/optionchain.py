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
