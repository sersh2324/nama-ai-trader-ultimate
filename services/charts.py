import plotly.graph_objects as go
from plotly.subplots import make_subplots


def price_chart(history, overlays, currency):
    bars = history.tail(250)
    candles = bars.dropna(subset=["Open"])
    figure = make_subplots(
        rows=2, cols=1, shared_xaxes=True, row_heights=[0.78, 0.22],
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
    figure.update_layout(height=560, margin={"l": 12, "r": 14, "t": 10, "b": 0},
                         legend={"orientation": "h", "y": 1.02},
                         hovermode="x unified", dragmode="pan")
    figure.update_xaxes(rangeslider_visible=False)
    figure.update_yaxes(title_text=currency, side="right", fixedrange=False, row=1, col=1)
    figure.update_yaxes(title_text="الحجم", side="right", fixedrange=True, row=2, col=1)
    return figure
