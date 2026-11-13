import pandas as pd
import sys
import types
sys.modules.setdefault("yfinance", types.ModuleType("yfinance"))
from services import market_data as m

def test_batch_download_multiple_tickers(monkeypatch):
    dates = pd.date_range("2025-01-01", periods=4)
    data = pd.DataFrame({("AAPL", "Open"): [1,2,3,4], ("AAPL", "High"): [2,3,4,5],
                         ("AAPL", "Low"): [1,2,3,4], ("AAPL", "Close"): [2,3,4,5],
                         ("AAPL", "Volume"): [10]*4,
                         ("MSFT", "Open"): [4,5,6,7], ("MSFT", "High"): [5,6,7,8],
                         ("MSFT", "Low"): [4,5,6,7], ("MSFT", "Close"): [5,6,7,8],
                         ("MSFT", "Volume"): [20]*4}, index=dates)
    data.columns = pd.MultiIndex.from_tuples(data.columns)
    monkeypatch.setattr(m.yf, "download", lambda *args, **kwargs: data, raising=False)
    found, errors = m.get_history_batch(["AAPL", "MSFT"])
    assert set(found) == {"AAPL", "MSFT"}
    assert not errors
    assert found["MSFT"]["Close"].iloc[-1] == 8

def test_batch_missing_symbol(monkeypatch):
    monkeypatch.setattr(m.yf, "download", lambda *args, **kwargs: pd.DataFrame(), raising=False)
    found, errors = m.get_history_batch(["UNKNOWN"])
    assert not found and len(errors) == 1
