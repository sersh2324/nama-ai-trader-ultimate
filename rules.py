import numpy as np
import pandas as pd

STRATEGIES = {
    "trend_following": "تتبع الاتجاه",
    "breakout": "اختراق المقاومة",
    "rsi_divergence": "تباعد RSI",
    "mean_reversion": "العودة إلى المتوسط",
    "multi_timeframe": "تأكيد الأطر الزمنية",
}

def _valid(v):
    try:
        return pd.notna(v) and np.isfinite(float(v))
    except Exception:
        return False

def evaluate_strategy(df: pd.DataFrame, strategy: str) -> dict:
    if df is None or len(df) < 60:
        return {"score": 0, "signal": "HOLD", "reasons": ["بيانات غير كافية"]}
    r = df.iloc[-1]
    p = float(r["Close"])
    score, reasons = 50, []
    e20, e50, e200 = r.get("EMA20"), r.get("EMA50"), r.get("EMA200")
    rsi, atr = r.get("RSI"), r.get("ATR")
    macd, macds = r.get("MACD"), r.get("MACD_Signal")
    volratio = r.get("Volume_Ratio")
    if strategy == "trend_following":
        checks = [
            (_valid(e20) and p > e20, 15, "السعر أعلى EMA20"),
            (_valid(e20) and _valid(e50) and e20 > e50, 20, "EMA20 أعلى EMA50"),
            (_valid(e200) and p > e200, 15, "السعر أعلى EMA200"),
            (_valid(macd) and _valid(macds) and macd > macds, 15, "زخم MACD إيجابي"),
            (_valid(rsi) and 50 <= rsi <= 70, 10, "RSI يدعم الاتجاه دون تشبع واضح"),
        ]
    elif strategy == "breakout":
        high20 = r.get("High20_Prev")
        checks = [
            (_valid(high20) and p > high20, 30, "إغلاق أعلى قمة 20 شمعة سابقة"),
            (_valid(volratio) and volratio >= 1.3, 20, "حجم التداول أعلى من متوسطه"),
            (_valid(e20) and p > e20, 10, "السعر أعلى EMA20"),
            (_valid(rsi) and 50 <= rsi <= 75, 10, "الزخم يدعم الاختراق"),
        ]
    elif strategy == "rsi_divergence":
        # Conservative bullish divergence proxy over recent confirmed bars.
        recent = df.tail(12)
        lows = recent["Low"]
        rs = recent["RSI"]
        bullish = False
        if len(recent) >= 8 and rs.notna().sum() >= 8:
            first, second = recent.iloc[-8:-3], recent.iloc[-3:]
            bullish = (second["Low"].min() < first["Low"].min() and
                       second["RSI"].min() > first["RSI"].min() and
                       _valid(rsi) and rsi < 55)
        checks = [
            (bullish, 35, "احتمال تباعد إيجابي بين السعر وRSI"),
            (_valid(macd) and _valid(macds) and macd > macds, 15, "تحسن زخم MACD"),
            (_valid(rsi) and rsi < 55, 10, "RSI ليس في تشبع شرائي"),
        ]
    elif strategy == "mean_reversion":
        lower = r.get("BB_Lower")
        mid = r.get("BB_Mid")
        checks = [
            (_valid(lower) and p < lower, 25, "السعر أسفل نطاق بولينجر السفلي"),
            (_valid(rsi) and rsi < 35, 25, "RSI يشير إلى ضغط بيعي"),
            (_valid(mid) and p < mid, 10, "السعر أسفل متوسط بولينجر"),
            (_valid(atr) and _valid(p) and atr / p < 0.08, 5, "التذبذب ضمن حد قابل للمراقبة"),
        ]
    else:  # multi_timeframe proxy from trend + momentum on same supplied frame
        checks = [
            (_valid(e20) and _valid(e50) and e20 > e50, 20, "الاتجاه القصير إيجابي"),
            (_valid(e200) and p > e200, 20, "الاتجاه طويل الأجل داعم"),
            (_valid(macd) and _valid(macds) and macd > macds, 15, "تأكيد الزخم"),
            (_valid(rsi) and 48 <= rsi <= 68, 10, "RSI ضمن نطاق متوازن"),
        ]
    for ok, pts, reason in checks:
        if ok:
            score += pts
            reasons.append(reason)
    if _valid(rsi) and rsi > 78:
        score -= 15
        reasons.append("تحذير: تشبع شرائي مرتفع")
    if _valid(r.get("ATR_Pct")) and r["ATR_Pct"] > 8:
        score -= 10
        reasons.append("تحذير: تذبذب مرتفع")
    score = int(np.clip(score, 0, 100))
    signal = "BUY" if score >= 70 else ("WATCH" if score >= 55 else "HOLD")
    return {"score": score, "signal": signal, "reasons": reasons,
            "strategy": strategy, "strategy_ar": STRATEGIES.get(strategy, strategy)}
