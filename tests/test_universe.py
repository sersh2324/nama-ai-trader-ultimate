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
    monkeypatch.setattr(u.yf, "screen", unavailable)
    sa, sa_warnings = discover("السعودي")
    us, us_warnings = discover("الأمريكي")
    both, warnings = discover("السوقان معًا")
    assert "2222.SR" in sa and "AAPL" not in sa
    assert "AAPL" in us and "2222.SR" not in us
    assert both == {**us, **sa}
    assert warnings == us_warnings + sa_warnings


def test_saudi_yahoo_directory_reads_all_pages(monkeypatch):
    from services import universe

    offsets = []

    def screen(query, *, offset, **kwargs):
        offsets.append(offset)
        if offset == 0:
            quotes = [{"symbol": f"{2000 + n}.SR", "longName": f"Company {n}",
                       "quoteType": "EQUITY"} for n in range(250)]
        else:
            quotes = [
                {"symbol": "4321.SR", "shortName": "Last company", "quoteType": "EQUITY"},
                {"symbol": "9400.SR", "shortName": "Fund", "quoteType": "ETF"},
            ]
        return {"total": 252, "quotes": quotes}

    monkeypatch.setattr(universe.yf, "screen", screen)
    companies, warnings = discover("السعودي")
    assert not warnings and offsets == [0, 250]
    assert companies["4321.SR"] == "Last company"
    assert "9400.SR" not in companies
    assert len(companies) >= 251
