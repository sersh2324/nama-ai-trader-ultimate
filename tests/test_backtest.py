import pandas as pd
import pytest

from services import backtest, scanner


def test_threshold_and_next_bar_stop_priority(monkeypatch):
    bars = pd.DataFrame(
        {"Open": 100, "High": 105, "Low": 95, "Close": 101, "ATR": 2},
        index=pd.date_range("2025-01-01", periods=61, freq="h"),
    )
    monkeypatch.setattr(backtest, "add_indicators", lambda raw: raw)
    monkeypatch.setattr(backtest, "evaluate_strategy", lambda frame, key: {"score": 65, "signal": "WATCH"})
    assert backtest.run_backtest(bars, threshold=70)[1]["trades"] == 0
    trades, stats = backtest.run_backtest(bars, threshold=65, fee_pct=0.2, slippage_pct=0.1)
    assert stats["trades"] == 1
    trade = trades.iloc[0]
    assert trade["signal_date"] == str(bars.index[-2])
    assert trade["entry_date"] == trade["exit_date"] == str(bars.index[-1])
    assert trade["exit"] == 97
    assert trade["return_pct"] == pytest.approx(-3.3)
    assert trade["reason"] == "وقف الخسارة"


def test_scanner_rejects_history_that_shrinks_below_warmup():
    bars = pd.DataFrame({"Close": [100] * 65})
    assert scanner.analyze_symbol("AAPL", bars) is None


def test_later_window_never_opens_a_trade_using_earlier_signals(monkeypatch):
    index = pd.date_range("2025-01-01", periods=91)
    raw = pd.DataFrame({"Open": 100, "Close": 101, "High": 102,
                        "Low": 99, "ATR": 2}, index=index)
    monkeypatch.setattr(backtest, "add_indicators", lambda value: value)
    monkeypatch.setattr(backtest, "evaluate_strategy", lambda *_: {"score": 90})
    trades, _ = backtest.run_backtest(raw, horizon=3, evaluate_from=index[70])
    assert not trades.empty
    assert pd.to_datetime(trades["signal_date"]).min() == index[70]
    assert pd.to_datetime(trades["entry_date"]).min() == index[71]


def test_scanner_uses_selected_threshold_and_shows_exit_rule(monkeypatch):
    bars = pd.DataFrame({"Open": 100, "High": 102, "Low": 99, "Close": 101, "Volume": 1000},
                        index=pd.date_range("2025-01-01", periods=60))
    monkeypatch.setattr(scanner, "evaluate_strategy", lambda _, key: {
        "score": 65, "strategy": key, "strategy_ar": key, "reasons": ["اختبار"],
    })
    result = scanner.analyze_symbol("AAPL", bars, selected_strategy="trend_following", threshold=65)
    assert result["signal"] == "شراء محتمل"
    assert result["stop"] < result["entry"] < result["target"]
    assert result["risk_reward"] > 1 and result["exit_rule"]
    assert scanner.analyze_symbol("AAPL", bars)["signal"] == "مراقبة"


def test_backtest_preserves_the_exit_candle_for_the_next_signal(monkeypatch):
    bars = pd.DataFrame(
        {"Open": 100, "High": 106, "Low": 99, "Close": 101, "ATR": 2},
        index=pd.date_range("2025-01-01", periods=63),
    )
    monkeypatch.setattr(backtest, "add_indicators", lambda raw: raw)
    monkeypatch.setattr(backtest, "evaluate_strategy", lambda *_: {"score": 90, "reasons": ["اختبار"]})
    trades, _ = backtest.run_backtest(bars)
    assert len(trades) == 3
    assert trades.iloc[1]["signal_date"] == trades.iloc[0]["exit_date"]
    assert trades.iloc[0]["signal_reason"] == "اختبار"
    assert trades.iloc[0]["risk_reward"] == pytest.approx(5 / 3)
