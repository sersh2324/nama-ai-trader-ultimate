from services.universe import discover

def test_discover_us(monkeypatch):
    import services.universe as u
    monkeypatch.setattr(u,'discover_us',lambda:({'AAPL':'Apple'},[]))
    assert discover('الأمريكي')[0]['AAPL']=='Apple'

def test_market_selection_and_directory_fallback(monkeypatch):
    import services.universe as u

    def unavailable(*args, **kwargs):
        raise OSError("offline")

    monkeypatch.setattr(u.requests, "get", unavailable)
    sa, sa_warnings = discover("السعودي")
    us, us_warnings = discover("الأمريكي")
    both, warnings = discover("السوقان معًا")
    assert "2222.SR" in sa and "AAPL" not in sa
    assert "AAPL" in us and "2222.SR" not in us
    assert both == {**us, **sa}
    assert warnings == us_warnings + sa_warnings
