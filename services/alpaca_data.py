"""Read-only US stock bars for the chart workspace."""

import os

import pandas as pd
import requests

from services.market_data import normalize_history

TIMEFRAMES = {
    "1m": "1Min", "5m": "5Min", "15m": "15Min", "30m": "30Min", "60m": "1Hour",
    "1h": "1Hour", "1d": "1Day", "1wk": "1Week", "1mo": "1Month",
}
BAR_COLUMNS = {"o": "Open", "h": "High", "l": "Low", "c": "Close", "v": "Volume"}


def alpaca_available(symbol):
    return bool(symbol and "." not in symbol and "^" not in symbol
                and os.getenv("APCA_API_KEY_ID") and os.getenv("APCA_API_SECRET_KEY"))


def unavailable(reason):
    frame = pd.DataFrame()
    frame.attrs["alpaca_status"] = reason
    return frame, None


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
    if feed not in {"iex", "sip", "delayed_sip"}:
        return unavailable("إعداد تغذية Alpaca غير صالح.")
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
        payload = response.json()
        grouped = payload.get("bars") if isinstance(payload, dict) else None
        bars = grouped.get(symbol) if isinstance(grouped, dict) else None
        if not isinstance(bars, list) or not bars:
            return unavailable("لم تُرجع التغذية شموعًا لهذا الرمز والفاصل.")
        frame = pd.DataFrame.from_records(bars)
        timestamps = pd.to_datetime(frame.pop("t"), utc=True, errors="coerce")
        frame.index = pd.DatetimeIndex(timestamps).tz_convert("America/New_York")
        frame = normalize_history(frame.loc[frame.index.notna()].rename(columns=BAR_COLUMNS))
    except requests.HTTPError as error:
        code = error.response.status_code if error.response is not None else None
        messages = {
            400: "رفض Alpaca معلمات طلب الأسعار.",
            401: "رفض Alpaca بيانات المصادقة. راجع إعدادات المفاتيح على الخادم.",
            403: "التغذية المطلوبة غير متاحة لهذا الحساب. راجع صلاحية SIP أو جرّب IEX من إعدادات الخادم.",
            429: "بلغ Alpaca حد الطلبات. أعد المحاولة بعد قليل.",
        }
        return unavailable(messages.get(code, "تعذّر جلب الأسعار من Alpaca."))
    except requests.Timeout:
        return unavailable("انتهت مهلة الاتصال بـ Alpaca.")
    except (requests.RequestException, KeyError, TypeError, ValueError):
        return unavailable("تعذّر الاتصال بـ Alpaca أو قراءة استجابته.")
    return (frame, feed) if not frame.empty else unavailable("لم تتوفر شموع صالحة في استجابة Alpaca.")
