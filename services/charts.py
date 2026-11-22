import plotly.graph_objects as go
from plotly.subplots import make_subplots


def price_chart(history, overlays, currency, levels=None, title=None, *, zones=None, panel=None, view_key=None):
    bars = history.tail(250)
    candles = bars.dropna(subset=["Open"])
    rows = 3 if panel else 2
    figure = make_subplots(
        rows=rows, cols=1, shared_xaxes=True,
        row_heights=[0.7, 0.12, 0.18] if panel else [0.78, 0.22],
        vertical_spacing=0.075,
    )
    up, down = "#28B88B", "#F26679"
    if candles.empty:
        figure.add_trace(go.Scatter(x=bars.index, y=bars["Close"], name="الإغلاق",
                                    line={"color": up}), row=1, col=1)
    else:
        figure.add_trace(go.Candlestick(
            x=candles.index, open=candles["Open"], high=candles["High"],
            low=candles["Low"], close=candles["Close"], name="السعر",
            increasing_line_color=up, decreasing_line_color=down,
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
    if zones:
        for key, label, color in (
            ("support", "دعم", "#28B88B"),
            ("resistance", "مقاومة", "#F26679"),
        ):
            bottom, top = zones[key]
            figure.add_hrect(y0=bottom, y1=top, fillcolor=color, opacity=0.18,
                             line_width=0, annotation_text=label, row=1, col=1)
    if title:
        figure.update_layout(title_text=title, margin_t=66)
    return figure
