from datetime import datetime, timezone

import pandas as pd

from services import monitoring, portfolio


def test_saved_scenarios_and_watchlists_are_private_and_idempotent(monkeypatch, tmp_path):
    monkeypatch.delenv("NAMA_DATABASE_URL", raising=False)
    monkeypatch.setattr(portfolio, "DB_PATH", tmp_path / "test.db")
    index = pd.date_range("2025-01-01", periods=5)
    frame = pd.DataFrame({"Close": [100, 104, 106, 109, 94],
                          "High": [101, 107, 107, 110, 95],
                          "Low": [99, 103, 105, 108, 93]}, index=index)
    scenario = {"as_of": str(index[0]), "reason": "سبب تجريبي",
                "setups": {"صعود": {"trigger": 105, "invalidation": 95, "targets": [108, 120]}}}
    item = monitoring.snapshot("AAPL", "2y", "1d", None, "صعود", scenario)
    key = monitoring.owner_key("issuer", "subject")
    other = monitoring.owner_key("issuer", "other")
    monitoring.save(key, item)
    monitoring.save(key, item)
    monitoring.save_watch(key, "AAPL", "الأمريكي")
    assert monitoring.records(other) == []
    assert monitoring.watch_rows(other) == []
    assert len(monitoring.watch_rows(key)) == 1
    (owner, item_id, saved, previous), = monitoring.records(key)
    now = datetime(2025, 1, 7, tzinfo=timezone.utc)
    confirmed, issue = monitoring.evaluate_saved(saved, previous, frame.iloc[:4], now)
    assert issue is None and confirmed["state"] == "تأكد"
    assert [event["kind"] for event in confirmed["events"]] == ["تأكد", "بلغ الهدف 1"]
    monitoring.write_progress(owner, item_id, previous, confirmed)
    cancelled, issue = monitoring.evaluate_saved(saved, confirmed, frame, now)
    assert issue is None and cancelled["state"] == "ألغي"
    assert len(cancelled["events"]) == 3
    monitoring.write_progress(owner, item_id, confirmed, cancelled)
    monitoring.write_progress(owner, item_id, previous, confirmed)
    assert monitoring.records(key)[0][3] == cancelled
    assert monitoring.evaluate_saved(saved, cancelled, frame, now) == (cancelled, None)

    unchanged, issue = monitoring.evaluate_saved(saved, confirmed, frame.iloc[1:], now)
    assert unchanged == confirmed and "الشمعة المرجعية" in issue
