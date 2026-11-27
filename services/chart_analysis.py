"""Price scenarios calculated from completed bars for the chart workspace."""

import pandas as pd

from services.news_engine import classify_headline


def chart_scenario(frame, *, last_bar_closed=False):
    completed = frame if last_bar_closed else frame.iloc[:-1]
    if len(completed) < 50:
        return None

    reference = completed.iloc[-1]
    recent = completed.tail(20)
    support = float(recent["Low"].min())
    resistance = float(recent["High"].max())
    if resistance <= support:
        return None

    close, fast, slow = reference[["Close", "EMA20", "EMA50"]]
    if close > fast > slow:
        trend = "صاعد"
    elif close < fast < slow:
        trend = "هابط"
    else:
        trend = "عرضي أو غير محسوم"

    width = (resistance - support) * 0.08
    return {
        "trend": trend,
        "close": float(close),
        "as_of": str(completed.index[-1]),
        "rsi": round(float(reference["RSI"]), 2) if pd.notna(reference["RSI"]) else None,
        "zones": {
            "support": (support, support + width),
            "resistance": (resistance - width, resistance),
        },
    }


def scenario_details(scenario, frame, articles):
    """Build fixed breakout levels and retain published evidence available at analysis."""
    support = scenario["zones"]["support"][0]
    resistance = scenario["zones"]["resistance"][1]
    width = resistance - support
    result = dict(scenario)
    result["setups"] = {
        "صعود": {"trigger": resistance, "invalidation": support,
                  "targets": [resistance + width / 2, resistance + width]},
        "هبوط": {"trigger": support, "invalidation": resistance,
                  "targets": [support - width / 2, support - width]},
    }
    result["setups"]["هبوط"]["targets"] = [
        target for target in result["setups"]["هبوط"]["targets"] if target > 0
    ]
    reference = frame.loc[:pd.Timestamp(scenario["as_of"])]
    last = reference.iloc[-1]
    result["reason"] = {
        "صاعد": "الإغلاق أعلى من EMA20، وEMA20 أعلى من EMA50.",
        "هابط": "الإغلاق أدنى من EMA20، وEMA20 أدنى من EMA50.",
        "عرضي أو غير محسوم": "ترتيب الإغلاق والمتوسطين EMA20 وEMA50 لا يدعم اتجاهًا واضحًا.",
    }[scenario["trend"]]
    average_volume = reference["Volume"].iloc[-21:-1].mean()
    result["volume_ratio"] = (
        round(float(last["Volume"] / average_volume), 2)
        if pd.notna(last["Volume"]) and pd.notna(average_volume) and average_volume > 0
        else None
    )
    result["news"] = articles
    return result


def recent_chart_news(articles, cutoff):
    """Select dated evidence known by the cutoff, omitting duplicate headlines."""
    evidence = []
    seen = set()
    cutoff = pd.to_datetime(cutoff, utc=True)
    for item in articles:
        headline = item["title"].strip()
        key = headline.casefold()
        date = item["date"]
        published = pd.to_datetime(int(date), unit="s", utc=True, errors="coerce") if date.isdigit() else (
            pd.to_datetime(date, utc=True, errors="coerce")
        )
        if (not headline or key in seen or pd.isna(published)
                or not cutoff - pd.Timedelta(days=7) <= published <= cutoff):
            continue
        seen.add(key)
        evidence.append({"title": headline, "source": str(item["source"] or "مصدر غير محدد"),
                         "url": item["url"], "published": published.isoformat(),
                         "tone": classify_headline(headline)})
    return sorted(evidence, key=lambda item: item["published"], reverse=True)[:5]


def track_scenario(scenario, direction, frame, horizon=20, *, last_bar_closed=False):
    """Evaluate closed bars after the anchor, preserving targets reached before cancellation."""
    setup = scenario["setups"][direction]
    sign = 1 if direction == "صعود" else -1
    anchor = pd.Timestamp(scenario["as_of"])
    completed = frame if last_bar_closed else frame.iloc[:-1]
    bars = completed.loc[completed.index > anchor].head(horizon)
    state = "بانتظار التأكيد"
    reason = "بانتظار إغلاق شمعة يتجاوز مستوى التأكيد."
    changed_at = None
    events = []
    targets = [{"price": price, "reached_at": None} for price in setup["targets"]]
    for timestamp, bar in bars.iterrows():
        close = bar["Close"]
        if sign * (close - setup["invalidation"]) < 0:
            state, reason = "ألغي", "أغلقت شمعة وراء مستوى الإلغاء."
            changed_at = str(timestamp)
            events.append({"kind": state, "at": changed_at})
            break
        if state == "بانتظار التأكيد":
            if sign * (close - setup["trigger"]) > 0:
                state, reason = "تأكد", "أغلقت شمعة وراء مستوى التأكيد."
                changed_at = str(timestamp)
                events.append({"kind": state, "at": changed_at})
            continue
        extreme = bar["High"] if sign == 1 else bar["Low"]
        for index, target in enumerate(targets, 1):
            if target["reached_at"] is None and sign * (extreme - target["price"]) >= 0:
                target["reached_at"] = str(timestamp)
                events.append({"kind": f"بلغ الهدف {index}", "at": target["reached_at"]})
        if targets and all(target["reached_at"] for target in targets):
            state, reason = "اكتملت الأهداف", "بلغت الشموع اللاحقة جميع الأهداف."
            changed_at = str(timestamp)
            events.append({"kind": state, "at": changed_at})
            break
    else:
        if len(bars) == horizon:
            state, reason = "انتهى", "انتهت مدة المتابعة المحددة بالشموع."
            changed_at = str(bars.index[-1])
            events.append({"kind": state, "at": changed_at})
    return {"state": state, "reason": reason, "at": changed_at, "targets": targets, "events": events}



def last_chart_bar_closed(timestamp, interval, now):
    """Use session-local bar starts and conservative boundaries for calendar bars."""
    start = pd.Timestamp(timestamp)
    current = pd.Timestamp(now).tz_convert(start.tz) if start.tz else pd.Timestamp(now).tz_localize(None)
    if interval.endswith("m"):
        end = start + pd.Timedelta(minutes=int(interval[:-1]))
    elif interval == "1h":
        end = start + pd.Timedelta(hours=1)
    elif interval == "1d":
        end = start.normalize() + pd.DateOffset(days=1)
    elif interval == "1wk":
        end = start.normalize() + pd.DateOffset(days=7)
    else:
        end = start.normalize() + pd.offsets.MonthBegin(1)
    return current >= end
