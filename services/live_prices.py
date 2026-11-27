"""Shared, read-only Alpaca stock-price stream and one-minute preview candles."""

import json
import math
import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass

import pandas as pd
from websockets.sync.client import connect

FEEDS = {"iex", "sip"}
COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


@dataclass
class Minute:
    start: pd.Timestamp
    opening: float
    high: float
    low: float
    close: float
    volume: float | None
    first: pd.Timestamp
    last: pd.Timestamp
    official: bool = False

    def record(self):
        return (self.start, self.opening, self.high, self.low, self.close, self.volume, self.official)


def apply_message(minutes, message):
    """Preview a minute from trades until its provider bar or revision arrives."""
    kind = message.get("T")
    if kind not in ("t", "b", "u"):
        return False
    try:
        stamp = pd.to_datetime(message["t"], utc=True)
        if pd.isna(stamp):
            return False
        minute = stamp.floor("min")
        if kind == "t":
            price = float(message["p"])
            if not math.isfinite(price) or price <= 0:
                return False
            current = minutes.get(minute)
            if current and current.official:
                return False
            if not current:
                minutes[minute] = Minute(minute, price, price, price, price, None, stamp, stamp)
            else:
                current.high, current.low = max(current.high, price), min(current.low, price)
                if stamp < current.first:
                    current.first, current.opening = stamp, price
                if stamp >= current.last:
                    current.last, current.close = stamp, price
        else:
            opening, high, low, close, volume = [float(message[key]) for key in ("o", "h", "l", "c", "v")]
            if not all(math.isfinite(value) for value in (opening, high, low, close, volume)):
                return False
            if low <= 0 or high < max(opening, low, close) or low > min(opening, close) or volume < 0:
                return False
            minutes[minute] = Minute(minute, opening, high, low, close, volume, stamp, stamp, True)
    except (KeyError, ValueError, TypeError, OverflowError):
        return False
    while len(minutes) > 180:
        del minutes[min(minutes)]
    return True


def merge_minutes(history, records, now=None):
    """Merge live rows with matching provider history, preserving a stable opening."""
    result = history.reindex(columns=COLUMNS).copy()
    if not records:
        return result
    result.index = pd.to_datetime(result.index, utc=True).tz_convert("America/New_York")
    current = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    for utc, opening, high, low, close, volume, official in records:
        at = utc.tz_convert(result.index.tz)
        if not official and utc < current.floor("min") and at in result.index:
            continue
        if not official and at in result.index:
            old = result.loc[at]
            opening = old["Open"] if pd.notna(old["Open"]) else opening
            high, low = max(high, old["High"]), min(low, old["Low"])
            volume = old["Volume"]
        result.loc[at] = [opening, high, low, close, volume]
    return result.sort_index()


class StockStream:
    """One worker per deployment process and feed, shared by all chart sessions."""

    def __init__(self, feed):
        self.feed = feed
        self.lock = threading.Lock()
        self.active = OrderedDict()
        self.minutes = {}
        self.latest = {}
        self.status = "يتصل"
        self.worker = None

    def read(self, symbol):
        with self.lock:
            self._expire()
            if symbol not in self.active and len(self.active) >= 12:
                return "خدمة البث ممتلئة مؤقتًا", [], None
            self.active[symbol] = time.monotonic()
            if self.worker is None:
                self.worker = threading.Thread(target=self._run, daemon=True)
                self.worker.start()
            rows = sorted(self.minutes.get(symbol, {}).values(), key=lambda row: row.start)
            return self.status, [row.record() for row in rows], self.latest.get(symbol)

    def _expire(self):
        cutoff = time.monotonic() - 25
        for symbol, seen in list(self.active.items()):
            if seen < cutoff:
                del self.active[symbol]
                self.minutes.pop(symbol, None)
                self.latest.pop(symbol, None)

    def _run(self):
        while True:
            with self.lock:
                self._expire()
                if not self.active:
                    self.status = "يتصل"
                    self.worker = None
                    return
            try:
                self._connection()
            except Exception:
                # Credentials and provider response bodies must stay out of the UI and logs.
                with self.lock:
                    if self.status not in ("رفض المزود الاتصال", "حد الاتصالات لدى المزود"):
                        self.status = "انقطع الاتصال، جارٍ إعادة المحاولة"
                time.sleep(5)

    def _connection(self):
        url = f"wss://stream.data.alpaca.markets/v2/{self.feed}"
        with connect(url, open_timeout=6, close_timeout=2) as socket:
            socket.send(json.dumps({"action": "auth", "key": os.environ["APCA_API_KEY_ID"],
                                    "secret": os.environ["APCA_API_SECRET_KEY"]}))
            subscribed = set()
            authenticated = False
            deadline = time.monotonic() + 8
            while True:
                with self.lock:
                    self._expire()
                    current = set(self.active)
                if not current:
                    return
                if authenticated:
                    for action, symbols in (("subscribe", current - subscribed),
                                            ("unsubscribe", subscribed - current)):
                        if symbols:
                            channels = {channel: sorted(symbols) for channel in ("trades", "bars", "updatedBars")}
                            socket.send(json.dumps({"action": action, **channels}))
                    subscribed = current
                elif time.monotonic() > deadline:
                    raise TimeoutError
                try:
                    messages = json.loads(socket.recv(timeout=0.75))
                except TimeoutError:
                    continue
                for message in messages:
                    with self.lock:
                        kind = message.get("T")
                        if kind == "success" and message.get("msg") == "authenticated":
                            authenticated = True
                            self.status = "متصل"
                        elif kind == "error":
                            self.status = "حد الاتصالات لدى المزود" if message.get("code") == 406 else "رفض المزود الاتصال"
                            raise ConnectionError
                        elif message.get("S") in self.active:
                            symbol = message["S"]
                            if apply_message(self.minutes.setdefault(symbol, {}), message) and kind == "t":
                                stamp = pd.to_datetime(message["t"], utc=True)
                                self.latest[symbol] = max(stamp, self.latest.get(symbol, stamp))
