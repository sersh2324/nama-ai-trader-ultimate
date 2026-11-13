import pandas as pd
import numpy as np
from services.indicators import rsi, add_indicators
from services.risk_manager import position_size

def test_rsi_no_losses_is_100():
    s = pd.Series(np.arange(1, 40, dtype=float))
    assert rsi(s).dropna().iloc[-1] == 100

def test_rsi_flat_is_50():
    s = pd.Series([10.0] * 40)
    assert rsi(s).dropna().iloc[-1] == 50

def test_position_size_respects_risk_and_allocation():
    x = position_size(20000, 1, 100, 95, 20)
    assert x["quantity"] == 40
    assert x["risk_amount"] == 200

def test_indicators_columns():
    idx = pd.date_range("2023-01-01", periods=260, freq="B")
    close = pd.Series(np.linspace(20, 50, len(idx)), index=idx)
    df = pd.DataFrame({"Open":close*.99, "High":close*1.01, "Low":close*.98,
                       "Close":close, "Volume":10000}, index=idx)
    out = add_indicators(df)
    for col in ["EMA20","EMA50","EMA200","RSI","MACD","ATR","ADX"]:
        assert col in out.columns