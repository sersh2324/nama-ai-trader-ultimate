"""Private saved scenarios and repeatable evaluation against closed price bars."""

import hashlib
import json
import os
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone

import pandas as pd

from services import portfolio
from services.alpaca_data import get_alpaca_history
from services.chart_analysis import last_chart_bar_closed, track_scenario
from services.market_data import get_history

TERMINAL_STATES = {"ألغي", "اكتملت الأهداف", "انتهى"}


def owner_key(issuer, subject):
    return hashlib.sha256(json.dumps([issuer, subject]).encode()).hexdigest()


def snapshot(symbol, period, interval, feed, direction, scenario):
    return {"symbol": symbol, "period": period, "interval": interval, "feed": feed,
            "direction": direction, "scenario": scenario, "horizon": 20,
            "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def scenario_id(item):
    scenario = item["scenario"]
    identity = [item["symbol"], item["interval"], item["feed"], item["direction"],
                scenario["as_of"], scenario["setups"][item["direction"]]]
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def initial_progress():
    return {"state": "بانتظار التأكيد", "events": []}


@contextmanager
def storage():
    dsn = os.getenv("NAMA_DATABASE_URL")
    if dsn:
        import psycopg

        connection = psycopg.connect(dsn, connect_timeout=5)
        marker = "%s"
    else:
        portfolio.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(portfolio.DB_PATH)
        marker = "?"
    with closing(connection), connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS saved_scenarios (
                owner TEXT NOT NULL, id TEXT NOT NULL, snapshot TEXT NOT NULL,
                progress TEXT NOT NULL, PRIMARY KEY (owner, id)
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS private_watchlist (
                owner TEXT NOT NULL, symbol TEXT NOT NULL, market TEXT NOT NULL,
                added_at TEXT NOT NULL, PRIMARY KEY (owner, symbol)
            )
        """)
        yield connection, marker


def save(owner, item):
    with storage() as (db, marker):
        fields = ", ".join([marker] * 4)
        db.execute(f"INSERT INTO saved_scenarios VALUES ({fields}) ON CONFLICT (owner, id) DO NOTHING",
                   (owner, scenario_id(item), json.dumps(item), json.dumps(initial_progress())))


def save_watch(owner, symbol, market):
    with storage() as (db, m):
        db.execute(f"INSERT INTO private_watchlist VALUES ({m}, {m}, {m}, {m}) "
                   "ON CONFLICT (owner, symbol) DO NOTHING",
                   (owner, symbol, market, datetime.now(timezone.utc).isoformat(timespec="seconds")))


def watch_rows(owner):
    with storage() as (db, m):
        return db.execute(f"SELECT symbol, market, added_at FROM private_watchlist WHERE owner = {m} ORDER BY symbol",
                          (owner,)).fetchall()


def records(owner=None):
    with storage() as (db, marker):
        query = "SELECT owner, id, snapshot, progress FROM saved_scenarios"
        rows = db.execute(query).fetchall() if owner is None else db.execute(
            f"{query} WHERE owner = {marker}", (owner,)).fetchall()
    return [(key, item_id, json.loads(item), json.loads(progress)) for key, item_id, item, progress in rows]


def write_progress(owner, item_id, previous, progress):
    if previous == progress:
        return
    with storage() as (db, m):
        db.execute(f"UPDATE saved_scenarios SET progress = {m} WHERE owner = {m} AND id = {m} AND progress = {m}",
                   (json.dumps(progress), owner, item_id, json.dumps(previous)))


def load_prices(item):
    symbol, period, interval = (item[key] for key in ("symbol", "period", "interval"))
    if item["feed"]:
        frame, actual_feed = get_alpaca_history(symbol, period, interval)
        return frame if actual_feed == item["feed"] else pd.DataFrame()
    return get_history(symbol, period, interval)


def evaluate_saved(item, previous, frame, now=None):
    if previous["state"] in TERMINAL_STATES:
        return previous, None
    if frame.empty:
        return previous, "تعذّر جلب البيانات من المصدر الأصلي."
    anchor = pd.Timestamp(item["scenario"]["as_of"])
    if anchor not in frame.index:
        return previous, "الشمعة المرجعية غير موجودة في السجل الحالي؛ احتُفظ بآخر حالة موثقة."
    market_zone = "Asia/Riyadh" if item["symbol"].endswith(".SR") else "America/New_York"
    last = pd.Timestamp(frame.index[-1])
    if last.tz is None:
        last = last.tz_localize(market_zone)
    closed = last_chart_bar_closed(last, item["interval"], now or datetime.now(timezone.utc))
    tracking = track_scenario(item["scenario"], item["direction"], frame, item["horizon"], last_bar_closed=closed)
    events = tracking["events"]
    if events[:len(previous["events"])] != previous["events"]:
        return previous, "تغيّر سجل المزود؛ احتُفظ بالحالة التي رُصدت سابقًا."
    return {"state": tracking["state"], "events": events, "reason": tracking["reason"],
            "at": tracking["at"], "targets": tracking["targets"]}, None


def refresh_all():
    """Run from an external scheduler against the same database as the site."""
    prices = {}
    for owner, item_id, item, previous in records():
        if previous["state"] in TERMINAL_STATES:
            continue
        cache_key = (item["symbol"], item["period"], item["interval"], item["feed"])
        if cache_key not in prices:
            prices[cache_key] = load_prices(item)
        progress, _ = evaluate_saved(item, previous, prices[cache_key])
        write_progress(owner, item_id, previous, progress)


if __name__ == "__main__":
    if not os.getenv("NAMA_DATABASE_URL"):
        raise SystemExit("Set NAMA_DATABASE_URL to the same durable database as the app.")
    refresh_all()
