import numpy as np
from services.indicators import add_indicators
from strategies.rules import STRATEGIES, evaluate_strategy

def analyze_symbol(symbol: str, raw, style="سوينغ", selected_strategy="auto", *, threshold=70):
    if raw is None or raw.empty or len(raw) < 60:
        return None
    frame = add_indicators(raw)
    if len(frame) < 60:
        return None
    row = frame.iloc[-1]
    price = float(row["Close"])
    if not np.isfinite(price) or price <= 0:
        return None
    atr = float(row["ATR"]) if row["ATR"] == row["ATR"] and row["ATR"] > 0 else price * .025
    if selected_strategy == "auto":
        candidates = [evaluate_strategy(frame, key) for key in STRATEGIES]
        best = max(candidates, key=lambda item: item["score"])
    else:
        best = evaluate_strategy(frame, selected_strategy)
    if style == "مضاربة يومية":
        stop_mult, target_mult = 1.0, 1.5
    elif style == "استثمار طويل الأجل":
        stop_mult, target_mult = 3.0, 5.0
    else:
        stop_mult, target_mult = 1.5, 2.5
    stop = max(0.0, price - stop_mult * atr)
    target = price + target_mult * atr
    risk = price - stop
    rr = (target - price) / risk if risk > 0 else None
    score = int(best["score"])
    signal = "شراء محتمل" if score >= threshold else ("مراقبة" if score >= 55 else "لا توجد إشارة")
    return {
        "symbol": symbol, "price": price, "score": score, "signal": signal,
        "strategy": best["strategy_ar"], "strategy_key": best["strategy"],
        "pattern": explain_pattern(frame, best["strategy"]),
        "reasons": best["reasons"], "rsi": float(row["RSI"]) if row["RSI"] == row["RSI"] else None,
        "atr_pct": float(row["ATR_Pct"]) if row["ATR_Pct"] == row["ATR_Pct"] else None,
        "entry": price, "stop": stop, "target": target, "risk_reward": rr,
        "exit_rule": "الخروج عند وقف الخسارة أو تحقق الهدف.",
        "frame": frame
    }


def explain_pattern(frame, strategy):
    current = frame.iloc[-1]
    previous = frame.iloc[-2]
    breakout_level = previous["High20_Prev"]
    if current["Close"] > current["High20_Prev"]:
        return "اختراق قمة 20 شمعة"
    if (previous["Close"] > breakout_level
            and current["Low"] <= breakout_level <= current["Close"]):
        return "إعادة اختبار الاختراق"
    support = frame["Low"].iloc[-21:-1].min()
    if current["Low"] <= support <= current["Close"] and current["Close"] > current["Open"]:
        return "ارتداد قرب دعم 20 شمعة"
    return STRATEGIES[strategy]
