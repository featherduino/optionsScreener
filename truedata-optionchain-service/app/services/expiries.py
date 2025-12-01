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
    formats = ["%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"]

    for e in expiries:
        # Drop any header-like values
        if isinstance(e, str) and e.strip().lower() in ("expiry", "expiries"):
            continue

        parsed_date = None
        for fmt in formats:
            try:
                parsed_date = datetime.strptime(e, fmt).date()
                break
            except Exception:
                continue

        if parsed_date:
            parsed.append((e, parsed_date))

    future = [x for x in parsed if x[1] >= today]
    pool = future if future else parsed

    pool.sort(key=lambda x: x[1])
    if not pool:
        return None

    return pool[0][0]
