from pathlib import Path

def test_scanner_controls_live_in_scanner_tab():
    text = Path(__file__).resolve().parents[1].joinpath('app.py').read_text(encoding='utf-8')
    scanner = text.split('with tabs[1]:', 1)[1].split('with tabs[2]:', 1)[0]
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
    for label in ("تحميل التحليل", "تحميل الأخبار والأساسيات", "تشغيل الاختبار التاريخي"):
        button(label).click().run()
        assert not app.exception
    assert app.session_state["bt_output"][2]["trades"] > 0
