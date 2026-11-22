from __future__ import annotations

import pandas as pd
import yfinance as yf

INTRADAY_PERIODS = {
    "1m": "7d", "2m": "30d", "5m": "60d", "15m": "60d",
    "30m": "60d", "60m": "730d", "1h": "730d",
}
PRICE_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


def normalize_history(raw: pd.DataFrame | None, symbol: str | None = None) -> pd.DataFrame:
    empty = pd.DataFrame(columns=PRICE_COLUMNS)
    if not isinstance(raw, pd.DataFrame) or raw.empty:
        return empty
    if isinstance(raw.columns, pd.MultiIndex):
        if raw.columns.nlevels != 2:
            return empty
        for level in range(raw.columns.nlevels):
            if symbol and symbol in raw.columns.get_level_values(level):
                raw = raw.xs(symbol, axis=1, level=level)
                break
        else:
            if symbol:
                return empty
            for level in (0, 1):
                if len(raw.columns.get_level_values(level).unique()) == 1:
                    raw = raw.droplevel(level, axis=1)
                    break
            else:
                return empty
    frame = raw.copy()
    frame.columns = [str(column).strip().title() for column in frame.columns]
    frame = frame.loc[:, ~frame.columns.duplicated()]
    frame = frame.reindex(columns=PRICE_COLUMNS).apply(pd.to_numeric, errors="coerce")
    frame = frame.replace([float("inf"), float("-inf")], float("nan"))
    frame = frame.dropna(subset=["High", "Low", "Close"]).sort_index(kind="stable")
    frame = frame[(frame["Low"] > 0) & (frame["High"] >= frame["Low"]) & (frame["Close"] > 0)]
    return frame[~frame.index.duplicated(keep="last")]


def _download(symbols, period, interval, **kwargs):
    if period in ("1y", "2y", "5y", "10y", "max"):
        period = INTRADAY_PERIODS.get(interval, period)
    return yf.download(symbols, period=period, interval=interval,
                       auto_adjust=True, progress=False, timeout=12, **kwargs)


def get_history(symbol: str, period="2y", interval="1d") -> pd.DataFrame:
    if not symbol:
        return normalize_history(None)
    try:
        raw = _download(symbol, period, interval, threads=False)
    except Exception:
        return normalize_history(None)
    return normalize_history(raw, symbol.upper())


def get_fundamentals_news(symbol: str) -> tuple[dict, list]:
    if not symbol:
        return {}, []
    try:
        ticker = yf.Ticker(symbol)
    except Exception:
        return {}, []
    try:
        info = ticker.get_info()
    except Exception:
        info = None
    try:
        raw_news = ticker.news
    except Exception:
        raw_news = None
    news = []
    for item in raw_news[:15] if isinstance(raw_news, (list, tuple)) else ():
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, dict):
            content = item
        canonical = content.get("canonicalUrl")
        provider = content.get("provider")
        url = (canonical.get("url") if isinstance(canonical, dict) else None) or item.get("link")
        source = (provider.get("displayName") if isinstance(provider, dict) else None) or item.get("publisher") or ""
        date = content.get("pubDate") or item.get("providerPublishTime") or ""
        title = content.get("title") or item.get("title") or "خبر بدون عنوان"
        news.append({"title": str(title), "url": url, "source": source, "date": str(date)})
    return info if isinstance(info, dict) else {}, news


def get_history_batch(symbols, period="2y", interval="1d", batch_size=15):
    """Return successful histories and diagnostics for symbols without data."""
    histories, errors = {}, []
    symbols = list(dict.fromkeys(s.strip().upper() for s in symbols if isinstance(s, str) and s.strip()))
    batch_size = max(1, batch_size)
    for start in range(0, len(symbols), batch_size):
        group = symbols[start:start + batch_size]
        raw = None
        if len(group) > 1:
            try:
                raw = _download(group, period, interval, threads=True, group_by="ticker")
            except Exception:
                pass
        if not isinstance(raw, pd.DataFrame) or not isinstance(raw.columns, pd.MultiIndex):
            raw = None
        for symbol in group:
            frame = normalize_history(raw, symbol)
            if frame.empty:
                frame = get_history(symbol, period, interval)
            if frame.empty:
                errors.append(f"{symbol}: لا تتوفر بيانات أسعار")
            else:
                histories[symbol] = frame
    return histories, errors


def get_option_expirations(symbol):
    try:
        return tuple(yf.Ticker(symbol).options)
    except Exception:
        return ()


def get_option_chain(symbol, expiration):
    try:
        chain = yf.Ticker(symbol).option_chain(expiration)
    except Exception:
        return pd.DataFrame(), pd.DataFrame()
    return chain.calls, chain.puts
