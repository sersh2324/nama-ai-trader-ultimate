import numpy as np
import pandas as pd
from services.indicators import add_indicators
from strategies.rules import evaluate_strategy

def run_backtest(raw, strategy="trend_following", threshold=70, horizon=15,
                 fee_pct=0.15, slippage_pct=0.10, stop_atr=1.5, target_atr=2.5):
    empty = {"trades": 0, "win_rate_pct": 0.0, "net_return_pct": 0.0,
             "max_drawdown_pct": 0.0, "profit_factor": 0.0, "expectancy_pct": 0.0}
    if raw is None or len(raw) < 100:
        return pd.DataFrame(), empty
    d = add_indicators(raw).dropna(subset=["ATR","RSI","EMA20","EMA50"])
    trades, i = [], 60
    costs = (fee_pct + slippage_pct) / 100.0
    while i < len(d) - 2:
        sig = evaluate_strategy(d.iloc[:i+1], strategy)
        if sig["score"] < threshold or sig["signal"] != "BUY":
            i += 1
            continue
        entry_i = i + 1
        entry = float(d["Open"].iloc[entry_i])
        atr = float(d["ATR"].iloc[i])
        if not np.isfinite(entry) or entry <= 0 or not np.isfinite(atr) or atr <= 0:
            i += 1
            continue
        stop, target = max(0, entry-stop_atr*atr), entry+target_atr*atr
        end_i = min(entry_i + horizon - 1, len(d)-1)
        exit_price, exit_i, reason = float(d["Close"].iloc[end_i]), end_i, "انتهاء مدة الاحتفاظ"
        for j in range(entry_i, end_i+1):
            op, lo, hi = map(float, (d["Open"].iloc[j], d["Low"].iloc[j], d["High"].iloc[j]))
            if op <= stop:
                exit_price, exit_i, reason = op, j, "وقف بعد فجوة"
                break
            if op >= target:
                exit_price, exit_i, reason = target, j, "هدف بعد فجوة"
                break
            # Conservative assumption if stop and target both hit in same candle.
            if lo <= stop:
                exit_price, exit_i, reason = stop, j, "وقف الخسارة"
                break
            if hi >= target:
                exit_price, exit_i, reason = target, j, "تحقق الهدف"
                break
        ret = (exit_price / entry - 1) - costs
        trades.append({"signal_date": str(d.index[i].date()),
                       "entry_date": str(d.index[entry_i].date()),
                       "exit_date": str(d.index[exit_i].date()),
                       "entry": entry, "exit": exit_price,
                       "return_pct": ret*100, "reason": reason,
                       "holding_bars": exit_i-entry_i+1,
                       "score": sig["score"]})
        i = exit_i + 1
    t = pd.DataFrame(trades)
    if t.empty:
        return t, empty
    rets = t["return_pct"].to_numpy()/100
    equity = np.cumprod(1+rets)
    curve = np.r_[1.0, equity]
    dd = curve/np.maximum.accumulate(curve)-1
    wins, losses = rets[rets>0], rets[rets<0]
    pf = wins.sum()/abs(losses.sum()) if len(losses) and abs(losses.sum()) else (float("inf") if len(wins) else 0.0)
    stats = {"trades": len(t), "win_rate_pct": round(float((rets>0).mean()*100),2),
             "net_return_pct": round(float((equity[-1]-1)*100),2),
             "max_drawdown_pct": round(float(dd.min()*100),2),
             "profit_factor": round(float(pf),2) if np.isfinite(pf) else "∞",
             "expectancy_pct": round(float(rets.mean()*100),3)}
    return t, stats
