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