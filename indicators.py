import numpy as np
import pandas as pd

def _series(s):
    return pd.to_numeric(s, errors="coerce").astype(float)

def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    close = _series(close)
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    # Correct edge cases: no losses -> 100; no gains and no losses -> 50.
    out = out.mask((avg_loss == 0) & (avg_gain > 0), 100)
    out = out.mask((avg_loss == 0) & (avg_gain == 0), 50)
    return out

def true_range(df: pd.DataFrame) -> pd.Series:
    prev = df["Close"].shift(1)
    parts = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - prev).abs(),
        (df["Low"] - prev).abs()
    ], axis=1)
    return parts.max(axis=1)

def wilder_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    tr = true_range(df)
    return tr.ewm(alpha=1/period, adjust=False, min_periods=period).mean()

def add_indicators(data: pd.DataFrame) -> pd.DataFrame:
    if data is None or data.empty:
        return pd.DataFrame()
    x = data.copy()
    for c in ["Open", "High", "Low", "Close", "Volume"]:
        if c not in x:
            x[c] = np.nan
        x[c] = _series(x[c])
    x = x.dropna(subset=["High", "Low", "Close"]).sort_index()
    c = x["Close"]
    for n in (20, 50, 200):
        x[f"EMA{n}"] = c.ewm(span=n, adjust=False, min_periods=min(n, 10)).mean()
    x["RSI"] = rsi(c, 14)
    fast = c.ewm(span=12, adjust=False).mean()
    slow = c.ewm(span=26, adjust=False).mean()
    x["MACD"] = fast - slow
    x["MACD_Signal"] = x["MACD"].ewm(span=9, adjust=False).mean()
    x["MACD_Hist"] = x["MACD"] - x["MACD_Signal"]
    x["ATR"] = wilder_atr(x, 14)
    x["ATR_Pct"] = x["ATR"] / c.replace(0, np.nan) * 100
    mid = c.rolling(20, min_periods=20).mean()
    sd = c.rolling(20, min_periods=20).std(ddof=0)
    x["BB_Mid"] = mid
    x["BB_Upper"] = mid + 2 * sd
    x["BB_Lower"] = mid - 2 * sd
    x["Volume_Avg20"] = x["Volume"].rolling(20, min_periods=10).mean()
    x["Volume_Ratio"] = x["Volume"] / x["Volume_Avg20"].replace(0, np.nan)
    x["High20_Prev"] = x["High"].rolling(20, min_periods=20).max().shift(1)
    x["Low20_Prev"] = x["Low"].rolling(20, min_periods=20).min().shift(1)
    # ADX / directional movement
    up = x["High"].diff()
    down = -x["Low"].diff()
    plus_dm = up.where((up > down) & (up > 0), 0.0)
    minus_dm = down.where((down > up) & (down > 0), 0.0)
    atr = x["ATR"].replace(0, np.nan)
    plus_di = 100 * plus_dm.ewm(alpha=1/14, adjust=False, min_periods=14).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1/14, adjust=False, min_periods=14).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    x["ADX"] = dx.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    x["Plus_DI"] = plus_di
    x["Minus_DI"] = minus_di
    # Daily-bar VWAP proxy; true intraday VWAP needs intraday data.
    typical = (x["High"] + x["Low"] + x["Close"]) / 3
    vol = x["Volume"].fillna(0)
    x["VWAP_20"] = (typical.mul(vol).rolling(20).sum() /
                    vol.rolling(20).sum().replace(0, np.nan))
    x["Return20_Pct"] = c.pct_change(20) * 100
    return x
