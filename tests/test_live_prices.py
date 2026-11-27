import pandas as pd

from services.live_prices import apply_message, merge_minutes


def trade(timestamp, price):
    return {"T": "t", "t": timestamp, "p": price}


def bar(kind, timestamp, opening, high, low, close, volume):
    return {"T": kind, "t": timestamp, "o": opening, "h": high, "l": low, "c": close, "v": volume}


def test_trade_sequence_moves_candle_and_opens_the_next_minute():
    minutes = {}
    assert apply_message(minutes, trade("2026-11-26T15:30:10Z", 100))
    assert apply_message(minutes, trade("2026-11-26T15:30:12Z", 103))
    assert apply_message(minutes, trade("2026-11-26T15:30:11Z", 98))
    assert apply_message(minutes, trade("2026-11-26T15:31:02Z", 102))
    first, second = sorted(minutes)
    assert minutes[first].record()[1:5] == (100, 103, 98, 103)
    assert minutes[second].record()[1:5] == (102, 102, 102, 102)

    assert apply_message(minutes, bar("b", "2026-11-26T15:30:00Z", 100, 102, 99, 101, 500))
    assert not apply_message(minutes, trade("2026-11-26T15:30:58Z", 110))
    assert minutes[first].record()[1:] == (100, 102, 99, 101, 500, True)
    assert apply_message(minutes, bar("u", "2026-11-26T15:30:00Z", 100, 103, 99, 102, 505))
    assert minutes[first].close == 102
    assert minutes[second].close == 102


def test_live_preview_keeps_historical_open_and_does_not_rewrite_closed_history():
    utc = pd.Timestamp("2026-11-26T15:30:00Z")
    history = pd.DataFrame({"Open": [98], "High": [101], "Low": [97],
                            "Close": [100], "Volume": [80]},
                           index=[utc.tz_convert("America/New_York")])
    preview = [(utc, 100, 103, 99, 102, None, False)]
    merged = merge_minutes(history, preview, now=utc + pd.Timedelta(seconds=50))
    assert merged.iloc[-1].tolist() == [98, 103, 97, 102, 80]
    later = merge_minutes(history, preview, now=utc + pd.Timedelta(minutes=1))
    assert later.iloc[-1]["Close"] == 100
    closed = [(utc, 98, 104, 97, 103, 120, True)]
    assert merge_minutes(history, closed, now=utc + pd.Timedelta(minutes=1)).iloc[-1]["Close"] == 103
    assert history.iloc[-1]["Close"] == 100


def test_chart_uses_live_minute_rows_when_provider_matches(monkeypatch, tmp_path):
    import json
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    from services import alpaca_data, live_prices, portfolio, universe

    now = pd.Timestamp.now(tz="UTC").floor("min")
    index = pd.date_range(end=now - pd.Timedelta(minutes=1), periods=70, freq="min").tz_convert("America/New_York")
    history = pd.DataFrame({"Open": 100.0, "High": 101.0, "Low": 99.0,
                            "Close": 100.0, "Volume": 200}, index=index)
    monkeypatch.setattr(portfolio, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(universe, "discover_us", lambda: ({"AAPL": "Apple"}, []))
    monkeypatch.setattr(alpaca_data, "alpaca_available", lambda _: True)
    monkeypatch.setattr(alpaca_data, "get_alpaca_history", lambda *_: (history, "iex"))
    monkeypatch.setenv("NAMA_ALPACA_FEED", "iex")

    live = [(now, 100.0, 104.0, 98.0, 102.0, None, False)]
    monkeypatch.setattr(live_prices.StockStream, "read", lambda *_: ("متصل", live, now))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
    app.radio(key="chart_quick_interval").set_value("1m").run()
    assert not app.exception
    spec = json.loads(app.get("plotly_chart")[0].proto.spec)
    assert len(spec["data"][0]["x"]) == 71
    assert any("شمعة قيد التكوّن" in item.value for item in app.caption)
    assert any("102.00" in item.value for item in app.metric)
