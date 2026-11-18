import pandas as pd
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


def test_none_and_malformed_news(monkeypatch):
    class Ticker:
        news = [None, {"content": None, "title": "Legacy"}, {"content": {"title": "Current"}}]

        def get_info(self):
            raise TypeError("NoneType")

    monkeypatch.setattr(m.yf, "Ticker", lambda symbol: Ticker())
    info, news = m.get_fundamentals_news("2222.SR")
    assert info == {}
    assert [item["title"] for item in news] == ["Legacy", "Current"]


def test_none_batch_falls_back_and_accepts_price_first_columns(monkeypatch):
    def download(symbol, **kwargs):
        if isinstance(symbol, list) or symbol == "MISSING":
            return None
        return pd.DataFrame(
            [[99, 102, 98, 100]],
            columns=pd.MultiIndex.from_product([["Open", "High", "Low", "Close"], [symbol]]),
        )

    monkeypatch.setattr(m.yf, "download", download)
    histories, errors = m.get_history_batch(["2222.SR", "MISSING"])
    assert histories["2222.SR"]["Close"].iloc[0] == 100
    assert len(errors) == 1 and errors[0].startswith("MISSING:")
    assert m.get_history("MISSING").empty
