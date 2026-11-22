from pathlib import Path

def test_scanner_controls_live_in_scanner_tab():
    text = Path(__file__).resolve().parents[1].joinpath('app.py').read_text(encoding='utf-8')
    scanner = text.split('with scanner_tab:', 1)[1].split('with chart_tab:', 1)[0]
    assert "scan_mode = st.radio" in scanner
    assert "st.button('🔎 بدء فحص الفرص'" in scanner
    assert 'if not scan_symbols:' in scanner

def test_manual_search_preserved():
    text = Path(__file__).resolve().parents[1].joinpath('app.py').read_text(encoding='utf-8')
    assert 'بحث باسم الشركة أو الرمز' in text
    assert 'إضافة رموز أخرى' in text

def test_streamlit_scan_and_market_switch(monkeypatch, tmp_path):
    import pandas as pd
    from streamlit.testing.v1 import AppTest

    from services import market_data, portfolio, universe

    monkeypatch.setattr(portfolio, "DB_PATH", tmp_path / "test.db")
    us_directory = {f"A{i:03}": f"Company {i}" for i in range(260)}
    us_directory.update({"AAPL": "Apple", "ZZZ": "Last test company"})
    monkeypatch.setattr(universe, "discover_us", lambda: (us_directory, []))
    monkeypatch.setattr(universe, "discover_sa", lambda: ({"2222.SR": "أرامكو"}, []))
    index = pd.date_range("2025-01-01", periods=90, freq="D")
    close = pd.Series(range(100, 190), index=index, dtype=float)
    bars = pd.DataFrame({"Open": close, "Close": close, "High": close + 1,
                         "Low": close - 1, "Volume": 1_000})
    monkeypatch.setattr(market_data, "get_history_batch",
                        lambda symbols, *_: ({s: bars for s in symbols}, []))
    monkeypatch.setattr(market_data, "get_history", lambda *_: bars)
    monkeypatch.setattr(market_data, "get_fundamentals_news", lambda *_: ({}, []))

    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()

    def button(label):
        return next(widget for widget in app.button if widget.label == label)

    assert not app.exception
    assert len(app.tabs) == 8
    directory = app.selectbox(key="detail_sym")
    assert directory.value == "AAPL"
    assert any("ZZZ" in option for option in directory.options)
    assert len(app.get("plotly_chart")) == 1
    directory.select("ZZZ").run()
    assert not app.exception
    assert app.session_state["detail"][0][0] == "ZZZ"
    app.selectbox(key="detail_sym").select("AAPL").run()
    app.radio(key="scan_mode").set_value("يدوي — الأسهم المختارة").run()
    app.multiselect[0].select("AAPL").run()
    button("🔎 بدء فحص الفرص").click().run()
    assert not app.exception
    assert app.session_state["scan_output"][1][0]["symbol"] == "AAPL"
    app.radio(key="market").set_value("السعودي").run()
    assert not app.exception
    assert app.selectbox(key="plan_sym").value == "2222.SR"
    assert any(item.value == "لم يتم الفحص بعد." for item in app.info)
    app.radio(key="scan_mode").set_value("تلقائي — دون اختيار أسهم").run()
    button("🔎 بدء فحص الفرص").click().run()
    assert not app.exception
    assert app.session_state["scan_output"][1][0]["symbol"] == "2222.SR"
    for label in ("تحديث الأسعار", "تحميل الأخبار والأساسيات", "تشغيل الاختبار التاريخي"):
        button(label).click().run()
        assert not app.exception
    assert app.session_state["bt_output"][2]["trades"] > 0


def test_opportunity_card_confirmation_and_options(monkeypatch):
    import pandas as pd
    from streamlit.testing.v1 import AppTest

    from services import opportunity_ui

    def bars(closes, start):
        frame = pd.DataFrame({"Close": closes, "Open": closes, "Volume": 1000},
                             index=pd.date_range(start, periods=len(closes)))
        frame["High"] = frame["Close"] + 1
        frame["Low"] = frame["Close"] - 1
        return frame

    opportunity = bars([50] * 30, "2025-01-01")
    later = bars([51.2, 51.3], "2025-01-31")
    monkeypatch.setattr(opportunity_ui, "get_history", lambda *_: later)
    monkeypatch.setattr(opportunity_ui, "get_option_expirations", lambda _: ("2025-02-21",))
    options = pd.DataFrame([{"contractSymbol": "TEST250221C00050000", "strike": 50,
                             "bid": 1.1, "ask": 1.2, "contractSize": "REGULAR"}])
    monkeypatch.setattr(opportunity_ui, "get_option_chain", lambda *_: (options, options.iloc[:0]))
    monkeypatch.setattr(opportunity_ui, "explain_opportunity", lambda _: "شرح تجريبي.")

    monkeypatch.setattr(opportunity_ui, "_test_frame", opportunity, raising=False)
    app = AppTest.from_string("""
from services.opportunity_ui import show_opportunity, _test_frame
show_opportunity({"symbol": "TEST", "price": 50, "reasons": ["اختبار"]},
                 _test_frame, "1y", "1d")
""").run()

    def click(label):
        next(button for button in app.button if button.label == label).click().run()
        assert not app.exception

    assert not app.exception
    assert len(app.get("plotly_chart")) == 1
    click("تابع شرط التأكيد")
    click("تحقق من الشرط")
    assert "51.2000" in app.success[0].value
    click("اشرح الفرصة بالذكاء الاصطناعي")
    assert any(item.value == "شرح تجريبي." for item in app.markdown)
    click("تحميل تواريخ العقود")
    assert app.dataframe[0].value["تكلفة العقد القياسي بالدولار"].iloc[0] == 120
