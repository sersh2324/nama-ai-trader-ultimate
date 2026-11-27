from collections import defaultdict
from math import isfinite

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def price_chart(history, overlays, currency, levels=None, title=None, *, zones=None, panel=None, view_key=None, chart_type="شموع",
                scenario_levels=None, full_range=False, workspace_interval=None,
                viewport_bars=60, fit_levels=False, interaction="pan"):
    bars = history if full_range or workspace_interval else history.tail(250)
    candles = bars.dropna(subset=["Open"])
    rows = 3 if panel else 2
    figure = make_subplots(
        rows=rows, cols=1, shared_xaxes=True,
        row_heights=[0.7, 0.12, 0.18] if panel else [0.78, 0.22],
        vertical_spacing=0.075,
    )
    up, down = ("#64E4B5", "#FF8E9D") if workspace_interval else ("#28B88B", "#F26679")
    candle_hover = {}
    if workspace_interval:
        candle_hover = {
            "text": [
                f"افتتاح {opening:,.2f}<br>أعلى {high:,.2f}<br>أدنى {low:,.2f}<br>إغلاق {close:,.2f}"
                for opening, high, low, close in candles[["Open", "High", "Low", "Close"]].itertuples(index=False, name=None)
            ],
            "hoverinfo": "x+text",
        }
    if candles.empty or chart_type == "خط":
        figure.add_trace(go.Scatter(x=bars.index, y=bars["Close"], name="الإغلاق",
                                    line={"color": up}), row=1, col=1)
    elif chart_type == "أعمدة سعرية":
        figure.add_trace(go.Ohlc(
            x=candles.index, open=candles["Open"], high=candles["High"],
            low=candles["Low"], close=candles["Close"], name="السعر",
            increasing_line_color=up, decreasing_line_color=down, **candle_hover,
        ), row=1, col=1)
    else:
        figure.add_trace(go.Candlestick(
            x=candles.index, open=candles["Open"], high=candles["High"],
            low=candles["Low"], close=candles["Close"], name="السعر",
            increasing_line_color=up, decreasing_line_color=down, **candle_hover,
        ), row=1, col=1)
    for name, color in overlays:
        figure.add_trace(go.Scatter(x=bars.index, y=bars[name], name=name,
                                    line={"color": color, "width": 1.5}), row=1, col=1)

    volume = bars.dropna(subset=["Volume"])
    if not volume.empty:
        colors = [up if close >= opening else down
                  for opening, close in zip(volume["Open"], volume["Close"])]
        figure.add_trace(go.Bar(x=volume.index, y=volume["Volume"], name="الحجم",
                                marker_color=colors, opacity=0.7), row=2, col=1)
    else:
        figure.add_annotation(text="حجم التداول غير متاح", x=0.5, y=0.5,
                              xref="x2 domain", yref="y2 domain", showarrow=False)
    if panel == "RSI":
        figure.add_trace(go.Scatter(x=bars.index, y=bars["RSI"], name="RSI"), row=3, col=1)
        for boundary in (30, 70):
            figure.add_hline(y=boundary, line_dash="dot", row=3, col=1)
        figure.update_yaxes(title_text="RSI", range=[0, 100], row=3, col=1)
    elif panel == "MACD":
        for name in ("MACD", "MACD_Signal"):
            figure.add_trace(go.Scatter(x=bars.index, y=bars[name], name=name), row=3, col=1)
        figure.add_trace(go.Bar(x=bars.index, y=bars["MACD_Hist"], name="MACD Hist"), row=3, col=1)
        figure.update_yaxes(title_text="MACD", row=3, col=1)

    figure.update_layout(height=650 if panel else 535, uirevision=view_key,
                         margin={"l": 12, "r": 14, "t": 10, "b": 0},
                         legend={"orientation": "h", "y": 1.02},
                         hovermode="x unified", dragmode="pan")
    figure.update_xaxes(rangeslider_visible=False)
    figure.update_yaxes(title_text=currency, side="right", fixedrange=False, row=1, col=1)
    figure.update_yaxes(title_text="الحجم", side="right", fixedrange=True, row=2, col=1)
    if levels:
        figure.add_hrect(y0=levels["trigger"], y1=levels["entry_ceiling"],
                         fillcolor="#3B82F6", opacity=0.16, line_width=0, row=1, col=1)
        for key, label, color in (
            ("trigger", "بداية منطقة الدخول", "#3B82F6"),
            ("entry_ceiling", "نهاية منطقة الدخول", "#3B82F6"),
            ("invalidation", "إلغاء الفكرة", down),
            ("objective", "هدف السيناريو", up),
        ):
            figure.add_hline(y=levels[key], line_dash="dot", line_color=color,
                             annotation_text=f"{label} · {levels[key]:,.4f}",
                             annotation_position="top left", row=1, col=1)
    if scenario_levels:
        for label, price, color in scenario_levels:
            figure.add_hline(y=price, line_dash="dot", line_color=color,
                             annotation_text=f"{label} · {price:,.2f}",
                             annotation_position="top right", row=1, col=1)
    if zones:
        for key, label, color in (
            ("support", "دعم", "#28B88B"),
            ("resistance", "مقاومة", "#F26679"),
        ):
            bottom, top = zones[key]
            figure.add_hrect(y0=bottom, y1=top, fillcolor=color, opacity=0.18,
                             line_width=0, annotation_text=label, row=1, col=1)
    if workspace_interval:
        visible = bars if full_range else bars.tail(viewport_bars)
        prices = [price for _, price, _ in scenario_levels or ()] if fit_levels else []
        if fit_levels and zones:
            prices.extend(price for band in zones.values() for price in band)
        style_workspace(figure, bars.index, visible, workspace_interval, panel, full_range,
                        [name for name, _ in overlays], prices, interaction)
    if title:
        figure.update_layout(title_text=title, margin_t=66)
    return figure



def style_workspace(figure, timestamps, visible, interval, panel, full_range, overlays, levels, interaction):
    """Show the latest candles at a readable scale while keeping the series pannable."""
    figure.update_layout(
        template="plotly_dark", paper_bgcolor="#10212A", plot_bgcolor="#10212A",
        height=555 if panel else 465, margin={"l": 8, "r": 12, "t": 35, "b": 16},
        dragmode=interaction, hovermode="closest",
        hoverlabel={"bgcolor": "#18353E", "font_color": "#F1F6F5", "align": "right"},
        newshape={"line": {"color": "#F4D28B", "width": 2}},
        font={"color": "#B7CDD1", "size": 12}, legend={"orientation": "h", "y": 1.08},
    )
    figure.update_xaxes(gridcolor="#263E48", showspikes=True, spikemode="across",
                       spikethickness=1, spikecolor="#A6BEC6")
    figure.update_yaxes(gridcolor="#263E48", zerolinecolor="#263E48", nticks=6)
    figure.update_yaxes(showspikes=True, spikemode="across", spikesnap="cursor",
                        spikethickness=1, spikecolor="#A6BEC6", automargin=True, row=1, col=1)
    hover_time = "%d %b %Y %H:%M" if interval.endswith("m") or interval == "1h" else "%d %b %Y"
    figure.update_xaxes(spikesnap="cursor", hoverformat=hover_time)
    visible_prices = visible[["Low", "High", *overlays]]
    low = min(float(visible_prices.min().min()), *(levels or [float("inf")]))
    high = max(float(visible_prices.max().max()), *(levels or [float("-inf")]))
    if isfinite(low) and isfinite(high):
        buffer = max((high - low) * 0.12, high * 0.001)
        figure.update_yaxes(range=[max(0, low - buffer), high + buffer], row=1, col=1)
    max_volume = float(visible["Volume"].max())
    if isfinite(max_volume) and max_volume > 0:
        figure.update_yaxes(range=[0, max_volume * 1.13], row=2, col=1)
    bar_minutes = {"5m": 5, "15m": 15, "30m": 30, "60m": 60, "1h": 60, "1d": 1440}.get(interval)
    if bar_minutes is None:
        bar_width = (timestamps[-1] - timestamps[-2]) if len(timestamps) > 1 else pd.Timedelta(days=7)
    else:
        bar_width = pd.Timedelta(minutes=bar_minutes)
        gaps = defaultdict(list)
        for previous, current in zip(timestamps[:-1], timestamps[1:]):
            gap = current - previous - bar_width
            # Keep isolated missing bars visible. Compress longer gaps such as overnight sessions.
            if gap >= 2 * bar_width:
                gaps[int(gap / pd.Timedelta(milliseconds=1))].append(previous + bar_width)
        if gaps:
            figure.update_xaxes(rangebreaks=[{"values": starts, "dvalue": duration}
                                             for duration, starts in gaps.items()])
    if not full_range:
        figure.update_xaxes(range=[visible.index[0] - bar_width / 2,
                                   timestamps[-1] + bar_width / 2])
