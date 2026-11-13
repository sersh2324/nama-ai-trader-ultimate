import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "nama.db"

def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)

def initialize():
    with _connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, market TEXT,
            symbol TEXT, side TEXT, quantity REAL, price REAL, fees REAL DEFAULT 0,
            notes TEXT)""")
        con.execute("""CREATE TABLE IF NOT EXISTS watchlist (
            symbol TEXT PRIMARY KEY, market TEXT, added_at TEXT)""")
        con.execute("""CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, symbol TEXT,
            score INTEGER, signal TEXT, strategy TEXT, message TEXT)""")

def add_trade(market, symbol, side, quantity, price, fees=0, notes=""):
    with _connect() as con:
        con.execute("INSERT INTO trades(created_at,market,symbol,side,quantity,price,fees,notes) VALUES(?,?,?,?,?,?,?,?)",
                    (datetime.now().isoformat(timespec="seconds"),market,symbol,side,quantity,price,fees,notes))

def get_trades():
    with _connect() as con:
        return __import__("pandas").read_sql_query("SELECT * FROM trades ORDER BY id DESC", con)

def clear_trades():
    with _connect() as con:
        con.execute("DELETE FROM trades")

def add_alert(symbol, score, signal, strategy, message):
    with _connect() as con:
        con.execute("INSERT INTO alerts(created_at,symbol,score,signal,strategy,message) VALUES(?,?,?,?,?,?)",
                    (datetime.now().isoformat(timespec="seconds"),symbol,score,signal,strategy,message))

def get_alerts():
    with _connect() as con:
        return __import__("pandas").read_sql_query("SELECT * FROM alerts ORDER BY id DESC LIMIT 300", con)

def clear_alerts():
    with _connect() as con:
        con.execute("DELETE FROM alerts")

def add_watch(symbol, market):
    with _connect() as con:
        con.execute("INSERT OR REPLACE INTO watchlist(symbol,market,added_at) VALUES(?,?,?)",
                    (symbol,market,datetime.now().isoformat(timespec="seconds")))

def get_watchlist():
    with _connect() as con:
        return __import__("pandas").read_sql_query("SELECT * FROM watchlist ORDER BY symbol", con)