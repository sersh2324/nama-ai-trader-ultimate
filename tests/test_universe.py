from services.universe import discover

def test_discover_us(monkeypatch):
    import services.universe as u
    monkeypatch.setattr(u,'discover_us',lambda:({'AAPL':'Apple'},[]))
    assert discover('الأمريكي')[0]['AAPL']=='Apple'