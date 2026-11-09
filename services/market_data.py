from __future__ import annotations
import pandas as pd
import yfinance as yf

INTRADAY_PERIODS = {
    "1m": "7d", "2m": "30d", "5m": "60d", "15m": "60d",
    "30m": "60d", "60m": "730d", "1h": "730d"
}

def normalize_history(raw: pd.DataFrame) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame(columns=["Open","High","Low","Close","Volume"])
    x = raw.copy()
    if isinstance(x.columns, pd.MultiIndex):
        x.columns = x.columns.get_level_values(0)
    x.columns = [str(c).title() for c in x.columns]
    needed = ["Open","High","Low","Close","Volume"]
    for c in needed:
        if c not in x:
            x[c] = float("nan")
        x[c] = pd.to_numeric(x[c], errors="coerce")
    x = x[needed].dropna(subset=["High","Low","Close"]).sort_index()
    x = x[~x.index.duplicated(keep="last")]
    return x

def get_history(symbol: str, period="2y", interval="1d") -> pd.DataFrame:
    if interval in INTRADAY_PERIODS:
        max_period = INTRADAY_PERIODS[interval]
        period = max_period if period in ("5y","2y","1y") else period
    raw = yf.download(symbol, period=period, interval=interval,
                      auto_adjust=True, progress=False, threads=False)
    return normalize_history(raw)

def get_fundamentals_news(symbol: str) -> tuple[dict, list]:
    ticker = yf.Ticker(symbol)
    try:
        info = ticker.get_info() or {}
    except Exception:
        info = {}
    try:
        raw_news = ticker.news or []
    except Exception:
        raw_news = []
    news = []
    for item in raw_news[:15]:
        content = item.get("content", item) if isinstance(item, dict) else {}
        if not isinstance(content, dict):
            content = item if isinstance(item, dict) else {}
        canonical = content.get("canonicalUrl")
        url = canonical.get("url") if isinstance(canonical, dict) else item.get("link")
        provider = content.get("provider")
        source = provider.get("displayName", "") if isinstance(provider, dict) else item.get("publisher", "")
        date = content.get("pubDate") or item.get("providerPublishTime") or ""
        title = content.get("title") or item.get("title") or "Ø®Ø¨Ø± Ø¨Ø¯ÙÙ Ø¹ÙÙØ§Ù"
        news.append({"title": title, "url": url, "source": source, "date": str(date)})
    return info, news
