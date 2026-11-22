"""Price scenarios calculated from completed bars for the chart workspace."""

import pandas as pd


def chart_scenario(frame):
    completed = frame.iloc[:-1]
    if len(completed) < 50:
        return None

    reference = completed.iloc[-1]
    recent = completed.tail(20)
    support = float(recent["Low"].min())
    resistance = float(recent["High"].max())
    if resistance <= support:
        return None

    close, fast, slow = reference[["Close", "EMA20", "EMA50"]]
    if close > fast > slow:
        trend = "صاعد"
    elif close < fast < slow:
        trend = "هابط"
    else:
        trend = "عرضي أو غير محسوم"

    width = (resistance - support) * 0.08
    return {
        "trend": trend,
        "close": float(close),
        "as_of": str(completed.index[-1]),
        "rsi": round(float(reference["RSI"]), 2) if pd.notna(reference["RSI"]) else None,
        "zones": {
            "support": (support, support + width),
            "resistance": (resistance - width, resistance),
        },
    }
