from urllib.parse import urlencode

import pandas as pd


def opportunity_levels(frame):
    # Leave out the newest bar, which the provider may still be updating.
    prior = frame.iloc[-21:-1]
    trigger = float(prior["High"].max())
    invalidation = float(prior.tail(5)["Low"].min())
    risk = trigger - invalidation
    return {
        "trigger": trigger,
        "entry_ceiling": trigger + risk * 0.25,
        "invalidation": invalidation,
        "objective": trigger + risk * 2,
    } if risk > 0 else None


def opportunity_status(close, levels):
    if close <= levels["invalidation"]:
        return "أُلغيت الفكرة"
    if close > levels["entry_ceiling"]:
        return "فاتت منطقة الدخول"
    if close > levels["trigger"]:
        return "داخل المنطقة حسب آخر سعر"
    return "بانتظار التأكيد"


def tradingview_link(symbol):
    ticker = f"TADAWUL:{symbol.removesuffix('.SR')}" if symbol.endswith(".SR") else symbol
    return "https://www.tradingview.com/chart/?" + urlencode({"symbol": ticker})


def option_quotes(table):
    fields = ["contractSymbol", "strike", "bid", "ask", "lastTradeDate",
              "volume", "openInterest", "impliedVolatility", "contractSize"]
    quotes = table.reindex(columns=fields).copy()
    bid = pd.to_numeric(quotes["bid"], errors="coerce").where(lambda price: price >= 0)
    ask = pd.to_numeric(quotes["ask"], errors="coerce").where(lambda price: price > 0)
    quotes["spread"] = (ask - bid).where(lambda spread: spread >= 0)
    quotes["premium"] = (ask * 100).where(quotes["contractSize"].eq("REGULAR"))
    return quotes
