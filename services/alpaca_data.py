"""Read-only US stock bars for the chart workspace."""

import os

import pandas as pd
import requests

from services.market_data import normalize_history

TIMEFRAMES = {
    "5m": "5Min", "15m": "15Min", "30m": "30Min", "60m": "1Hour",
    "1h": "1Hour", "1d": "1Day", "1wk": "1Week", "1mo": "1Month",
}
BAR_COLUMNS = {"o": "Open", "h": "High", "l": "Low", "c": "Close", "v": "Volume"}


def alpaca_available(symbol):
    return bool(symbol and "." not in symbol and "^" not in symbol
                and os.getenv("APCA_API_KEY_ID") and os.getenv("APCA_API_SECRET_KEY"))


def get_alpaca_history(symbol, period, interval):
    """Return chart history and the actual feed, or an empty frame on failure."""
    if not alpaca_available(symbol) or interval not in TIMEFRAMES:
        return pd.DataFrame(), None

    unit = next((unit for unit in ("mo", "y", "d") if period.endswith(unit)), "")
    amount = period.removesuffix(unit) if unit else ""
    if not amount.isdigit() or int(amount) <= 0:
        return pd.DataFrame(), None
    start = pd.Timestamp.now(tz="UTC") - pd.DateOffset(
        **{{"mo": "months", "y": "years", "d": "days"}[unit]: int(amount)}
    )
    feed = os.getenv("NAMA_ALPACA_FEED", "iex").strip().lower()
    try:
        response = requests.get(
            "https://data.alpaca.markets/v2/stocks/bars",
            params={"symbols": symbol, "timeframe": TIMEFRAMES[interval],
                    "start": start.isoformat(), "sort": "desc", "limit": 1000,
                    "adjustment": "all", "feed": feed},
            headers={"APCA-API-KEY-ID": os.environ["APCA_API_KEY_ID"],
                     "APCA-API-SECRET-KEY": os.environ["APCA_API_SECRET_KEY"]},
            timeout=8,
        )
        response.raise_for_status()
        bars = response.json()["bars"][symbol]
        frame = pd.DataFrame.from_records(bars)
        timestamps = pd.to_datetime(frame.pop("t"), utc=True, errors="coerce")
        frame.index = pd.DatetimeIndex(timestamps).tz_convert("America/New_York")
        frame = normalize_history(frame.loc[frame.index.notna()].rename(columns=BAR_COLUMNS))
    except (requests.RequestException, KeyError, TypeError, ValueError):
        return pd.DataFrame(), None
    return frame, feed if not frame.empty else None
