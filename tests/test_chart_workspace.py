import json
from pathlib import Path

import pandas as pd
import pytest
import requests
import streamlit as st
from streamlit.testing.v1 import AppTest

from services import alpaca_data, market_data, opportunity_explanation, portfolio, universe
from services.chart_analysis import chart_scenario
from services.charts import price_chart
from services.indicators import add_indicators
from services.opportunities import opportunity_levels, opportunity_status, option_quotes


def bars(closes):
    frame = pd.DataFrame({"Close": closes, "Open": closes, "Volume": 1000},
                         index=pd.date_range("2025-01-01", periods=len(closes)))
    frame["High"] = frame["Close"] + 1
    frame["Low"] = frame["Close"] - 1
    return frame


@pytest.mark.parametrize(("closes", "trend"), [
    (list(range(100, 161)), "صاعد"),
    (list(range(160, 99, -1)), "هابط"),
    ([100] * 61, "عرضي أو غير محسوم"),
])
def test_scenario_uses_completed_bars(closes, trend):
    original = chart_scenario(add_indicators(bars(closes)))
    closes[-1] = 999
    frame = add_indicators(bars(closes))
    assert chart_scenario(frame) == original
    assert original["trend"] == trend
    assert original["zones"]["support"][0] == min(closes[-21:-1]) - 1
    assert original["zones"]["resistance"][1] == max(closes[-21:-1]) + 1
    assert chart_scenario(frame.head(50)) is None


def test_chart_renders_selected_overlays_zones_and_missing_volume():
    frame = add_indicators(bars(list(range(100, 400))))
    figure = price_chart(frame, [("EMA20", "#ffffff")], "USD", panel="MACD",
                         zones={"support": (370, 375), "resistance": (395, 400)})
    assert [trace.type for trace in figure.data] == ["candlestick", "scatter", "bar", "scatter", "scatter", "bar"]
    assert len(figure.data[0].x) == 250
    assert [(shape.y0, shape.y1) for shape in figure.layout.shapes] == [(370, 375), (395, 400)]

    frame[["Open", "Volume"]] = float("nan")
    figure = price_chart(frame, [], "SAR", panel="RSI")
    assert [trace.type for trace in figure.data] == ["scatter", "scatter"]
    assert {item.text for item in figure.layout.annotations} == {"حجم التداول غير متاح"}
    assert [shape.y0 for shape in figure.layout.shapes] == [30, 70]


def test_opportunity_levels_and_status_boundaries():
    frame = bars([50] * 30 + [500])
    levels = opportunity_levels(frame)
    assert levels == {"trigger": 51, "entry_ceiling": 51.5, "invalidation": 49, "objective": 55}
    assert opportunity_status(49, levels) == "أُلغيت الفكرة"
    assert opportunity_status(51, levels) == "بانتظار التأكيد"
    assert opportunity_status(51.5, levels) == "داخل المنطقة حسب آخر سعر"
    assert opportunity_status(51.51, levels) == "فاتت منطقة الدخول"
    figure = price_chart(frame, [], "USD", levels=levels)
    assert [(shape.y0, shape.y1) for shape in figure.layout.shapes] == [
        (51, 51.5), (51, 51), (51.5, 51.5), (49, 49), (55, 55),
    ]


def test_invalid_quotes_and_nonstandard_contracts():
    table = pd.DataFrame([
        {"bid": "1.20", "ask": "1.40", "contractSize": "REGULAR"},
        {"bid": 2, "ask": 1, "contractSize": "MINI"},
        {"bid": -1, "ask": 0, "contractSize": "REGULAR"},
    ])
    result = option_quotes(table)
    assert result.loc[0, "premium"] == 140
    assert result.loc[0, "spread"] == pytest.approx(0.2)
    assert result.loc[1:, ["spread", "premium"]].isna().all().all()


def test_alpaca_bars_request_and_fallback(monkeypatch):
    monkeypatch.setenv("APCA_API_KEY_ID", "test-id")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "test-secret")
    monkeypatch.setenv("NAMA_ALPACA_FEED", "sip")

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"bars": {"AAPL": [
                {"t": "2025-01-02T14:30:00Z", "o": 10, "h": 12, "l": 9, "c": 11, "v": 40},
                {"t": "2025-01-01T14:30:00Z", "o": 9, "h": 11, "l": 8, "c": 10, "v": 30},
            ]}}

    def fetch(url, *, params, headers, timeout):
        assert url == "https://data.alpaca.markets/v2/stocks/bars"
        assert params["symbols"] == "AAPL" and params["timeframe"] == "5Min"
        assert params["feed"] == "sip" and params["sort"] == "desc"
        assert headers["APCA-API-KEY-ID"] == "test-id"
        assert timeout > 0
        return Response()

    monkeypatch.setattr(alpaca_data.requests, "get", fetch)
    frame, feed = alpaca_data.get_alpaca_history("AAPL", "5d", "5m")
    assert feed == "sip" and frame["Close"].tolist() == [10, 11]
    assert str(frame.index.tz) == "America/New_York"
    assert alpaca_data.get_alpaca_history("2222.SR", "5d", "5m")[0].empty

    def unavailable(*args, **kwargs):
        raise requests.Timeout

    monkeypatch.setattr(alpaca_data.requests, "get", unavailable)
    frame, feed = alpaca_data.get_alpaca_history("AAPL", "5d", "5m")
    assert frame.empty and feed is None


def test_chart_first_ai_indicators_and_source_switch(monkeypatch, tmp_path):
    st.cache_data.clear()
    monkeypatch.setattr(portfolio, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(universe, "discover_us", lambda: ({"AAPL": "Apple", "MSFT": "Microsoft"}, []))
    monkeypatch.setattr(universe, "discover_sa", lambda: ({"2222.SR": "أرامكو"}, []))
    monkeypatch.setattr(alpaca_data, "alpaca_available", lambda symbol: not symbol.endswith(".SR"))
    history_calls = []

    def alpaca_history(symbol, period, interval):
        history_calls.append((symbol, period, interval))
        if symbol == "AAPL":
            return bars(range(100, 170)), "iex"
        return pd.DataFrame(), None

    monkeypatch.setattr(alpaca_data, "get_alpaca_history", alpaca_history)
    monkeypatch.setattr(market_data, "get_history", lambda *_: bars(range(200, 270)))
    monkeypatch.setattr(market_data, "get_fundamentals_news", lambda _: ({}, []))

    def explain(facts, *, prompt):
        assert json.loads(facts)["symbol"] == "AAPL"
        assert "الدعم" in prompt
        return "شرح تجريبي للمستويات"

    monkeypatch.setattr(opportunity_explanation, "explain_opportunity", explain)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()

    def chart():
        assert not app.exception
        return json.loads(app.get("plotly_chart")[0].proto.spec)

    def button(label):
        return next(widget for widget in app.button if widget.label == label)

    assert app.tabs[0].label == "الشارت والتحليل"
    assert any("Alpaca" in caption.value for caption in app.caption)
    assert chart()["layout"]["paper_bgcolor"] == "#10212A"
    assert len(chart()["data"][0]["x"]) == 70
    assert chart()["layout"]["xaxis"]["range"][0].startswith("2025-01-10")
    app.radio(key="chart_quick_interval").set_value("5m").run()
    assert history_calls[-1] == ("AAPL", "30d", "5m")
    assert any("الفاصل 5 دقائق" in caption.value for caption in app.caption)
    next(widget for widget in app.checkbox if widget.label == "استخدم إعدادات الفترة المتقدمة").check().run()
    app.checkbox(key="chart_ema").check().run()

    next(widget for widget in app.selectbox if widget.label == "مدة الشمعة").select("1wk").run()
    assert history_calls[-1] == ("AAPL", "2y", "1wk")
    next(widget for widget in app.selectbox if widget.label == "نطاق البيانات").select("1y").run()
    assert history_calls[-1] == ("AAPL", "1y", "1wk")
    button("حلّل بالذكاء الاصطناعي").click().run()
    assert len(chart()["layout"]["shapes"]) == 6
    next(widget for widget in app.selectbox if widget.label == "نوع الشارت").select("خط").run()
    assert chart()["data"][0]["type"] == "scatter"
    next(widget for widget in app.selectbox if widget.label == "نوع الشارت").select("أعمدة سعرية").run()
    assert chart()["data"][0]["type"] == "ohlc"
    assert any(item.value == "شرح تجريبي للمستويات" for item in app.markdown)
    app.toggle(key="chart_historical").set_value(True).run()
    date_picker = next(widget for widget in app.date_input if widget.label.startswith("نطاق تاريخ الشارت"))
    dates = app.session_state.detail[1].index.date
    date_picker.set_value((dates[-10], dates[-1])).run()
    assert len(chart()["data"][0]["x"]) == 10
    app.toggle(key="chart_historical").set_value(False).run()
    app.checkbox(key="chart_bands").check().run()
    next(widget for widget in app.selectbox if widget.label == "مؤشر إضافي").select("RSI").run()
    assert {"EMA20", "BB_Upper", "RSI"} <= {trace["name"] for trace in chart()["data"]}
    app.selectbox(key="detail_sym").select("MSFT").run()
    assert not chart()["layout"].get("shapes") or all(
        shape["xref"].startswith("x3") for shape in chart()["layout"]["shapes"]
    )
    assert app.session_state.detail[1]["Close"].iloc[-1] == 269
    assert any("Yahoo Finance" in caption.value for caption in app.caption)
    assert any("تعذّرت بيانات Alpaca" in item.value for item in app.info)
    app.radio(key="market").set_value("السعودي").run()
    assert not app.exception and app.selectbox(key="detail_sym").value == "2222.SR"
    assert not any("تحديث كل 30 ثانية" == widget.label for widget in app.checkbox)


@pytest.mark.parametrize(("closes", "message"), [
    ([48, 52, 53], "أُلغيت الفكرة قبل التأكيد."),
    ([50, 53], "لم يتحقق الشرط في الشموع الأحدث."),
    ([53], "ما وصلت شمعة مكتملة أحدث من شمعة الفرصة."),
    ([], "تعذر تحديث الأسعار."),
])
def test_opportunity_confirmation_edge_cases(monkeypatch, closes, message):
    from services import opportunity_ui

    recent = bars(closes)
    recent.index = pd.date_range("2025-01-31", periods=len(closes), tz="UTC")
    monkeypatch.setattr(opportunity_ui, "get_history", lambda *_: recent)
    app = AppTest.from_string("""
from services.opportunity_ui import watch_confirmation
watch_confirmation("AAPL", "1y", "1d", "2025-01-30", {"trigger": 51, "invalidation": 49})
""").run()
    assert not app.exception and not app.success
    assert message in [element.value for element in [*app.warning, *app.info]]


def test_option_selection_and_uncovered_symbols(monkeypatch):
    from services import opportunity_ui

    st.cache_data.clear()
    dates = ("2025-02-21", "2025-03-21")
    monkeypatch.setattr(opportunity_ui, "get_option_expirations",
                        lambda symbol: dates if symbol == "AAPL" else ())
    requests_made = []

    def chain(symbol, expiration):
        requests_made.append((symbol, expiration))
        calls = pd.DataFrame([{"contractSymbol": "CALL", "ask": 2, "contractSize": "REGULAR"}])
        puts = pd.DataFrame([{"contractSymbol": "PUT", "ask": 3, "contractSize": "REGULAR"}])
        return calls, puts if expiration == dates[0] else puts.iloc[:0]

    monkeypatch.setattr(opportunity_ui, "get_option_chain", chain)
    app = AppTest.from_string("""
import streamlit as st
from services.opportunity_ui import show_options
symbol = st.selectbox("السهم", ["AAPL", "MSFT", "2222.SR"])
show_options(symbol)
""").run()
    app.button[0].click().run()
    assert app.dataframe[0].value["رمز العقد"].tolist() == ["CALL"]
    app.radio[0].set_value("شراء Put").run()
    assert app.dataframe[0].value["تكلفة العقد القياسي بالدولار"].tolist() == [300]
    app.selectbox(key="expiry-AAPL").select(dates[1]).run()
    assert requests_made[-1] == ("AAPL", dates[1])
    assert any("لا توجد أسعار عقود" in item.value for item in app.info)
    app.selectbox[0].select("MSFT").run()
    app.button[0].click().run()
    assert any("تعذر تحميل تواريخ الخيارات" in item.value for item in app.info)
    app.selectbox[0].select("2222.SR").run()
    assert not app.exception and not app.button


def test_options_provider_failure(monkeypatch):
    def unavailable(symbol):
        raise requests.Timeout

    monkeypatch.setattr(market_data.yf, "Ticker", unavailable)
    assert market_data.get_option_expirations("AAPL") == ()
    calls, puts = market_data.get_option_chain("AAPL", "2025-03-21")
    assert calls.empty and puts.empty



def test_tracks_confirmation_targets_and_invalidation_from_closed_bars():
    from services.chart_analysis import track_scenario

    frame = bars([100, 104, 106, 109, 94])
    frame.loc[frame.index[1], "High"] = 108
    scenario = {"as_of": str(frame.index[0]), "setups": {
        "صعود": {"trigger": 105, "invalidation": 95, "targets": [108, 120]},
        "هبوط": {"trigger": 95, "invalidation": 105, "targets": [90]},
    }}
    assert track_scenario(scenario, "صعود", frame.iloc[:2], last_bar_closed=True)["state"] == "بانتظار التأكيد"
    pending = track_scenario(scenario, "صعود", frame)
    assert pending["state"] == "تأكد"
    assert pending["targets"][0]["reached_at"] == str(frame.index[3])
    closed = track_scenario(scenario, "صعود", frame, last_bar_closed=True)
    assert closed["state"] == "ألغي"
    assert closed["targets"][1]["reached_at"] is None


def test_chart_news_uses_only_dated_headlines_known_by_cutoff():
    from services.chart_analysis import recent_chart_news

    articles = [{"title": title, "date": date, "source": "Feed", "url": None}
                for title, date in [("Profit growth", "2026-11-24"), ("Profit growth", "2026-11-24"),
                                    ("Old loss", "2026-10-01"), ("Future upgrade", "2026-11-26"),
                                    ("Undated report", "")]]
    evidence = recent_chart_news(articles, "2026-11-25")
    assert [item["title"] for item in evidence] == ["Profit growth"]
    assert evidence[0]["tone"] == "إيجابي مبدئي"



def test_workspace_scale_uses_visible_candles_without_hiding_history():
    frame = bars([250] * 100 + [26.1, 26.2, 26.3] * 10)
    levels = [("الهدف", 35, "#64E4B5")]
    fig = price_chart(frame, [], "SAR", workspace_interval="1d",
                      viewport_bars=30, scenario_levels=levels, interaction="zoom")
    assert len(fig.data[0].x) == 130
    assert fig.layout.yaxis.range[1] < 29
    assert fig.layout.xaxis.range[0] == frame.index[-30] - pd.Timedelta(hours=12)
    assert fig.layout.yaxis.showspikes and fig.layout.xaxis.showspikes
    assert fig.layout.dragmode == "zoom"
    assert "افتتاح" in fig.data[0].text[-1] and "إغلاق" in fig.data[0].text[-1]
    assert fig.layout.shapes[0].y0 == 35

    with_levels = price_chart(frame, [], "SAR", workspace_interval="1d",
                              viewport_bars=30, scenario_levels=levels, fit_levels=True)
    assert with_levels.layout.yaxis.range[1] > 35


def test_alpaca_permission_error_is_sanitized(monkeypatch):
    monkeypatch.setenv("APCA_API_KEY_ID", "test-id")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "test-secret")
    monkeypatch.setenv("NAMA_ALPACA_FEED", "sip")

    def denied(*args, **kwargs):
        response = requests.Response()
        response.status_code = 403
        raise requests.HTTPError("test-secret provider body", response=response)

    monkeypatch.setattr(alpaca_data.requests, "get", denied)
    frame, feed = alpaca_data.get_alpaca_history("AAPL", "2y", "1d")
    assert feed is None and frame.empty
    assert "SIP" in frame.attrs["alpaca_status"]
    assert "test-secret" not in frame.attrs["alpaca_status"]
