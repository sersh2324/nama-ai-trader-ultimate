import json
from datetime import datetime, timezone
from time import monotonic
import pandas as pd
import requests
import streamlit as st

from services.alpaca_data import alpaca_available, get_alpaca_history
from services.chart_analysis import (chart_scenario, last_chart_bar_closed, recent_chart_news,
                                     scenario_details, track_scenario)
from services.charts import price_chart
from services.opportunity_explanation import explain_opportunity
from services.opportunity_ui import show_opportunity
from services.indicators import add_indicators
from services.market_data import get_history, get_history_batch, get_fundamentals_news
from services.universe import discover
from services.scanner import analyze_symbol
from services.backtest import run_backtest
from services.risk_manager import position_size
from services.portfolio import (initialize, add_trade, get_trades, clear_trades,
                                add_alert, get_alerts, clear_alerts, add_watch, get_watchlist)
from services.symbols import SA, US, company_name
from strategies.rules import STRATEGIES
from services.news_engine import classify_headline
from services.workspace_ui import WORKSPACE_STYLE

VERSION = "1.5.0-beta"
CHART_PROMPT = (
    "اشرح للمبتدئ بالعربية الاتجاه ومناطق الدعم والمقاومة والأخبار المعروضة إن وجدت. "
    "اعتمد حصراً على القيم الواردة. اذكر أن السيناريو مشروط بالإغلاق خارج النطاق. "
    "صف الخبر كمحفز محتمل، ولا تنسب إليه حركة السعر من دون دليل. لا تخترع أهدافاً أو أخباراً."
)
st.set_page_config(page_title="NAMA AI Trader", page_icon="📈", layout="wide",
                   initial_sidebar_state="collapsed")
initialize()
st.markdown(WORKSPACE_STYLE, unsafe_allow_html=True)

watch_selection = st.session_state.pop("open_watch_symbol", None)
if watch_selection:
    st.session_state.workspace_tab = "الشارت والتحليل"
    st.session_state.last_opened_watch_symbol = watch_selection
    st.session_state.market = "السعودي" if watch_selection.endswith(".SR") else "الأمريكي"

market_column, directory_column = st.columns([2, 3], vertical_alignment="bottom")
market = market_column.radio("السوق", ["الأمريكي", "السعودي", "السوقان معًا"],
                            horizontal=True, key="market")
time_settings = st.sidebar.popover("إعدادات الفترة والفاصل للماسح والأدوات")
style = time_settings.selectbox("نمط التداول", ["مضاربة يومية", "سوينغ", "استثمار طويل الأجل"], index=1)
intervals, periods, period_default = {
    "مضاربة يومية": (["5m", "15m", "30m", "60m"], ["5d", "30d", "60d"], 1),
    "سوينغ": (["1h", "1d", "1wk"], ["6mo", "1y", "2y", "5y"], 2),
    "استثمار طويل الأجل": (["1d", "1wk", "1mo"], ["2y", "5y", "10y"], 1),
}[style]
interval_names = {
    "5m": "5 دقائق", "15m": "15 دقيقة", "30m": "30 دقيقة", "60m": "ساعة",
    "1h": "ساعة", "1d": "يومي", "1wk": "أسبوعي", "1mo": "شهري",
}
interval = time_settings.selectbox("مدة الشمعة", intervals, index=1, format_func=interval_names.get)
period = time_settings.selectbox("نطاق البيانات", periods, index=period_default)

with st.sidebar:
    st.header("إعدادات الماسح والاختبار")
    strategy_choice = st.selectbox("الاستراتيجية", ["auto"] + list(STRATEGIES),
        format_func=lambda x: "اختيار تلقائي" if x == "auto" else STRATEGIES[x])
    threshold = st.slider("حد جودة الإشارة", 50, 95, 70, 1)
    fee_pct = st.number_input("تكاليف الصفقة الإجمالية %", 0.0, 5.0, 0.15, 0.05)
    slippage_pct = st.number_input("الانزلاق السعري %", 0.0, 5.0, 0.10, 0.05)

@st.cache_data(ttl=3600, show_spinner=False)
def load_universe(market_name):
    return discover(market_name)

with st.spinner('جارٍ تحميل دليل الأسهم...'):
    universe, discovery_warnings = load_universe(market)
def company_label(symbol):
    primary = universe.get(symbol, symbol)
    alias = company_name(symbol)
    if alias != symbol and alias != primary:
        if alias.startswith(primary + " — "):
            primary = alias
        else:
            primary = f"{primary} · {alias}"
    return f"{primary} ({symbol})"


options = sorted(universe)
popular = list(dict.fromkeys([*US, *SA]))
picker_options = [symbol for symbol in popular if symbol in universe]
picker_options.extend(symbol for symbol in options if symbol not in US and symbol not in SA)
with st.sidebar.expander("أسهم الماسح اليدوي وإضافة رموز"):
    selected = st.multiselect("أسهم الماسح اليدوي", picker_options,
                              format_func=company_label, max_selections=100)
    manual = st.text_input("إضافة رموز أخرى (افصل بينها بفاصلة)", "")
manual_symbols = []
for value in manual.split(','):
    symbol = value.strip().upper()
    if symbol.isascii() and symbol.isdigit() and len(symbol) in (4, 5) and market != "الأمريكي":
        symbol += ".SR"
    if symbol:
        manual_symbols.append(symbol)
symbols = list(dict.fromkeys(selected + manual_symbols))[:100]
saved_lookup = st.session_state.get("last_opened_watch_symbol")
if saved_lookup:
    saved_market = "السعودي" if saved_lookup.endswith(".SR") else "الأمريكي"
    if market not in (saved_market, "السوقان معًا"):
        saved_lookup = None
analysis_options = list(dict.fromkeys(picker_options + manual_symbols + (
    [saved_lookup] if saved_lookup else []
)))
if watch_selection:
    st.session_state.detail_sym = watch_selection
detail_symbol = directory_column.selectbox("بحث باسم الشركة أو الرمز", analysis_options,
                             format_func=company_label, key="detail_sym",
                             placeholder="ابحث عن سهم")
if discovery_warnings:
    with st.expander('حالة تحميل دليل الشركات — مصادر بديلة أو أخطاء'):
        for warning in discovery_warnings:
            st.warning(warning)

chart_tab, scanner_tab, watch_tab, portfolio_tab, market_tab, plan_tab, backtest_tab, news_tab, alerts_tab = st.tabs([
    "الشارت والتحليل", "اكتشاف الفرص", "المراقبة", "المحفظة", "لوحة السوق",
    "خطة الصفقة", "الاختبار التاريخي", "الأخبار والأساسيات", "التنبيهات",
], key="workspace_tab", on_change="rerun")

with market_tab:
    st.subheader("لوحة السوق")
    st.write(f"السوق: **{market}** | نمط التداول: **{style}** | الإطار: **{interval}**")
    st.info("مصادر البيانات المجانية قد تكون متأخرة أو محدودة. لا تُعامل الأسعار على أنها لحظية ما لم يؤكد مزود البيانات ذلك.")
    market_metrics = st.columns(3)
    market_metrics[0].metric("الرموز المتاحة", f"{len(options):,}")
    market_metrics[1].metric("أسهم الماسح اليدوي", len(symbols))
    market_metrics[2].metric("السهم المختار", detail_symbol or "—")

with scanner_tab:
    st.subheader('🔎 اكتشاف الفرص — الماسح التلقائي')
    st.caption('جميع إعدادات الماسح وزر بدء الفحص موجودة في هذا التبويب.')
    st.info(f'السوق: {market} | الشركات المتاحة: {len(options)} | الإطار الزمني: {interval}')
    scan_mode = st.radio('طريقة الفحص', ['تلقائي — دون اختيار أسهم', 'يدوي — الأسهم المختارة'], horizontal=True, key='scan_mode')
    auto_scan = scan_mode.startswith('تلقائي')
    if auto_scan:
        scan_limit = st.select_slider('عدد الأسهم في دورة الفحص', options=[25,50,100,250,500,1000], value=25, key='scan_limit')
        scan_offset = st.number_input('بداية الدفعة — لفحص بقية الأسهم', min_value=0,
                                      max_value=max(0,len(options)-1), value=0, step=25, key=f"scan_offset-{market}")
        scan_symbols = options[int(scan_offset):int(scan_offset)+int(scan_limit)]
    else:
        scan_symbols = symbols
        st.caption(f'عدد الرموز المختارة يدويًا: {len(symbols)}. غيّرها من «أسهم الماسح اليدوي» في القائمة الجانبية.')
    st.write(f'**عدد الرموز التي سيحاول الماسح فحصها: {len(scan_symbols)}**')
    if not scan_symbols:
        st.error('لا توجد رموز للفحص. تحقق من تحميل دليل الشركات، أو أضف رمزًا يدويًا ثم اختر الوضع اليدوي.')
    if auto_scan and discovery_warnings:
        st.warning('قد تكون القائمة محدودة بسبب تعذر بعض مصادر دليل الشركات. راجع حالة تحميل دليل الشركات أعلاه.')
    scan_key = (market, style, interval, period, strategy_choice, threshold, tuple(scan_symbols))
    if st.button('🔎 بدء فحص الفرص', type='primary', disabled=not scan_symbols):
        rows, errors, snapshots = [], [], {}
        bar = st.progress(0)
        progress_text = st.empty()
        for start in range(0,len(scan_symbols),15):
            batch=scan_symbols[start:start+15]
            progress_text.caption(f"جارٍ فحص {min(start+len(batch),len(scan_symbols))} من {len(scan_symbols)} رمزًا")
            histories,batch_errors=get_history_batch(batch,period,interval)
            errors.extend(batch_errors)
            for sym in batch:
                try:
                    result=analyze_symbol(sym,histories.get(sym),style,strategy_choice)
                    if result:
                        snapshots[sym] = result.pop('frame').tail(80).copy()
                        result['company']=universe.get(sym,company_name(sym))
                        rows.append(result)
                        if result['score'] >= threshold:
                            add_alert(sym,result['score'],result['signal'],result['strategy'],'؛ '.join(result['reasons']))
                    elif sym in histories:
                        errors.append(f'{sym}: insufficient history')
                except Exception as exc:
                    errors.append(f'{sym}: {str(exc)[:120]}')
            bar.progress(min(1.0,(start+len(batch))/len(scan_symbols)))
        bar.empty()
        progress_text.empty()
        rows.sort(key=lambda r:r['score'],reverse=True)
        st.session_state.scan_output = (scan_key, rows, errors, datetime.now().strftime('%Y-%m-%d %H:%M'), snapshots)
    scan_output = st.session_state.get("scan_output")
    scan_completed = scan_output is not None and scan_output[0] == scan_key
    results = []
    if scan_completed:
        _, results, errors, scan_time, snapshots = scan_output
        st.caption(f"آخر فحص: {scan_time} | المطلوب: {len(scan_symbols)} | تم تحليله: {len(results)}")
        if errors:
            with st.expander(f'ملاحظات الفحص ({len(errors)})'):
                st.write('\n'.join(errors[:200]))
    if results:
        candidates = [r for r in results if r["score"] >= threshold and r["signal"] != "لا توجد إشارة"]
        if candidates:
            st.subheader("الفرص المطابقة للفلتر")
            by_symbol = {r["symbol"]: r for r in candidates}
            selected_opportunity = st.selectbox("اختر فرصة لعرض الشارت", by_symbol,
                                                format_func=company_label)
            show_opportunity(by_symbol[selected_opportunity], snapshots[selected_opportunity], period, interval)
        else:
            st.info("اكتمل الفحص. ما ظهرت فرص مطابقة لحد التقييم الحالي.")
        with st.expander("كل نتائج الفحص"):
            table = pd.DataFrame([{k: v for k, v in r.items() if k not in ("reasons", "strategy_key")}
                                  for r in results])
            st.dataframe(table, width="stretch", hide_index=True)
            st.download_button("تنزيل النتائج CSV", table.to_csv(index=False).encode("utf-8-sig"),
                               "nama_scan_results.csv", "text/csv")

    else:
        if scan_completed:
            st.warning("انتهى الفحص دون نتائج قابلة للعرض. قد تكون الأسعار غير متاحة أو التاريخ غير كافٍ. جرّب 1d وسوينغ، وراجع ملاحظات البيانات.")
        else:
            st.info("لم يتم الفحص بعد.")

with chart_tab:
    if not detail_symbol:
        st.info("اختر السوق ثم ابحث عن السهم لعرض الشارت.")
    else:
        st.subheader(company_label(detail_symbol))
        quick_periods = {"5m": "30d", "15m": "30d", "1h": "60d", "1d": "2y", "1wk": "5y"}
        quick_labels = {"5m": "5 د", "15m": "15 د", "1h": "ساعة", "1d": "يوم", "1wk": "أسبوع"}
        quick_interval = st.radio("فاصل الشارت", list(quick_periods), horizontal=True, index=3,
                                  format_func=quick_labels.get, key="chart_quick_interval")
        chart_period, chart_interval = quick_periods[quick_interval], quick_interval
        can_refresh_live = alpaca_available(detail_symbol)
        with st.container(horizontal=True, gap="small"):
            controls = st.popover("المؤشرات والرسم")
            history_controls = st.popover("الفترة والتاريخ")
        custom_period = history_controls.checkbox("استخدم إعدادات الفترة المتقدمة")
        if custom_period:
            chart_period, chart_interval = period, interval
        ema = controls.checkbox("المتوسطات EMA", value=False, key="chart_ema")
        bands = controls.checkbox("نطاقات بولينجر", key="chart_bands")
        panel = controls.selectbox("مؤشر إضافي", [None, "RSI", "MACD"],
                                      format_func=lambda value: value or "بدون")
        chart_type = controls.selectbox("نوع الشارت", ["شموع", "خط", "أعمدة سعرية"])
        live = (controls.checkbox("تحديث كل 30 ثانية", value=True, key="chart_live")
                if can_refresh_live else controls.checkbox("متابعة الأسعار كل دقيقتين", value=False))
        historical = history_controls.toggle("اختيار تاريخ البداية والنهاية", key="chart_historical")
        poll_interval = ("30s" if can_refresh_live else "120s") if live and not historical else None
        overlays = []
        if ema:
            overlays.extend([("EMA20", "#e7ae55"), ("EMA50", "#6299ed"), ("EMA200", "#ac84ee")])
        if bands:
            overlays.extend([("BB_Upper", "#8e9caf"), ("BB_Lower", "#8e9caf")])

        @st.fragment(run_every=poll_interval)
        def show_stock_chart():
            detail_key = (detail_symbol, chart_period, chart_interval)
            refresh = st.session_state.pop("chart_refresh_requested", False)
            analyze = st.session_state.pop("chart_analysis_requested", False)
            detail = st.session_state.get("detail")
            fetched_at = st.session_state.get("chart_fetched_at", 0)
            poll_due = poll_interval and monotonic() - fetched_at >= (29 if can_refresh_live else 119)
            if refresh or not detail or detail[0] != detail_key or poll_due:
                with st.spinner("جارٍ جلب أسعار السهم..."):
                    raw, feed = get_alpaca_history(detail_symbol, chart_period, chart_interval)
                    if raw.empty:
                        raw = get_history(detail_symbol, chart_period, chart_interval)
                    stale = raw.empty and detail and detail[0] == detail_key and not detail[1].empty
                    if not stale:
                        detail = (detail_key, add_indicators(raw), feed)
                        st.session_state.detail = detail
                        st.session_state.chart_received_at = datetime.now(timezone.utc)
                    st.session_state.chart_stale = bool(stale)
                    st.session_state.chart_fetched_at = monotonic()

            _, frame, feed = detail
            if frame.empty:
                st.info("لم تتوفر أسعار لهذا الرمز والفاصل. جرّب فاصلًا آخر أو حدّث البيانات.")
                st.button("تحديث الأسعار", on_click=st.session_state.__setitem__,
                          args=("chart_refresh_requested", True))
                return

            currency = "SAR" if detail_symbol.endswith(".SR") else "USD"
            source = f"Alpaca · {feed.upper()}" if feed else "Yahoo Finance · قد تتأخر البيانات"
            analysis_frame = frame
            display_frame = frame
            date_range = None
            if historical:
                dates = frame.index.date
                date_range = st.date_input(
                    "نطاق تاريخ الشارت ضمن البيانات المحمّلة", (dates[0], dates[-1]),
                    min_value=dates[0], max_value=dates[-1], key=f"chart_dates_{detail_key}",
                )
                if len(date_range) != 2:
                    st.info("اختر تاريخ البداية والنهاية.")
                    return
                analysis_frame = frame.loc[dates <= date_range[1]]
                display_frame = frame.loc[(dates >= date_range[0]) & (dates <= date_range[1])]
                if display_frame.empty:
                    st.info("لا توجد شموع ضمن هذا النطاق.")
                    return
            last = display_frame.iloc[-1]
            previous = analysis_frame["Close"].iloc[-2] if len(analysis_frame) > 1 else None
            change = f"{(last['Close'] / previous - 1):+.2%}" if previous else None
            st.metric("إغلاق آخر شمعة معروضة" if historical else "آخر سعر داخل الشمعة",
                      f"{last['Close']:,.2f} {currency}", change,
                      help="التغيّر مقارنة بإغلاق الشمعة السابقة على نفس الفاصل.")
            received_at = st.session_state.get("chart_received_at")
            received_label = received_at.strftime("%H:%M:%S UTC") if received_at else "غير مسجل"
            analysis_key = (detail_key, feed, date_range)
            market_zone = "Asia/Riyadh" if currency == "SAR" else "America/New_York"
            bar_start = pd.Timestamp(analysis_frame.index[-1])
            if bar_start.tz is None:
                bar_start = bar_start.tz_localize(market_zone)
            last_closed = last_chart_bar_closed(bar_start, chart_interval, datetime.now(timezone.utc))
            if analyze:
                scenario = chart_scenario(analysis_frame, last_bar_closed=last_closed)
                if scenario is None:
                    st.info("يلزم 50 شمعة سابقة على الأقل ونطاق سعري صالح لرسم السيناريو.")
                    st.session_state.pop("chart_analysis", None)
                else:
                    _, articles = get_fundamentals_news(detail_symbol)
                    cutoff = datetime.now(timezone.utc)
                    if historical:
                        cutoff = min(bar_start, cutoff)
                    scenario = scenario_details(scenario, analysis_frame, recent_chart_news(articles, cutoff))
                    facts = dict(scenario, symbol=detail_symbol, interval=chart_interval, currency=currency)
                    try:
                        with st.spinner("جارٍ شرح الاتجاه والمستويات..."):
                            explanation = explain_opportunity(json.dumps(facts, ensure_ascii=False),
                                                              prompt=CHART_PROMPT)
                    except (requests.RequestException, KeyError, TypeError, IndexError, ValueError):
                        explanation = None
                    st.session_state.chart_analysis = (analysis_key, scenario, explanation)

            saved = st.session_state.get("chart_analysis")
            scenario, explanation = saved[1:] if saved and saved[0] == analysis_key else (None, None)
            zones = scenario["zones"] if scenario else None
            direction = None
            tracking = None
            chart_levels = []
            if scenario:
                preferred = "هبوط" if scenario["trend"] == "هابط" else "صعود"
                direction_key = f"setup_{analysis_key}"
                direction = st.session_state.get(direction_key, preferred)
                setup = scenario["setups"][direction]
                tracking = track_scenario(scenario, direction, analysis_frame, last_bar_closed=last_closed)
                chart_levels = [("التأكيد", setup["trigger"], "#F4D28B"),
                                ("الإلغاء", setup["invalidation"], "#FF8E9D")]
                chart_levels.extend((f"الهدف {index}", target, "#64E4B5")
                                    for index, target in enumerate(setup["targets"], 1))
            st.plotly_chart(price_chart(display_frame, overlays, currency, zones=zones, panel=panel,
                                        view_key=str(analysis_key), chart_type=chart_type,
                                        scenario_levels=chart_levels, full_range=historical,
                                        workspace_interval=chart_interval), width="stretch",
                            theme=None, config={"displaylogo": False, "scrollZoom": True}, key="price_chart")
            st.caption(f"{source} · بداية آخر شمعة معروضة {display_frame.index[-1]} · "
                       f"آخر جلب ناجح {received_label} · الفاصل {interval_names[chart_interval]}")
            if st.session_state.chart_stale:
                st.warning("تعذّر تحديث السعر. تظهر آخر بيانات متاحة.")
            if can_refresh_live and not feed:
                st.info("تعذّرت بيانات Alpaca لهذا السهم أو الفاصل. الشارت يعرض المصدر البديل.")

            analyze_action, refresh_action, watch_action = st.columns([2, 1, 1])
            analyze_action.button("حلّل بالذكاء الاصطناعي", type="primary", width="stretch",
                                  on_click=st.session_state.__setitem__,
                                  args=("chart_analysis_requested", True))
            refresh_action.button("تحديث الأسعار", width="stretch",
                                  on_click=st.session_state.__setitem__,
                                  args=("chart_refresh_requested", True))
            if watch_action.button("حفظ للمراقبة", width="stretch"):
                add_watch(detail_symbol, "السعودي" if currency == "SAR" else "الأمريكي")
                st.toast("تم حفظ السهم في المراقبة.")
            if scenario:
                with st.container(border=True, key="scenario_card"):
                    bias = {"صاعد": "صعود محتمل", "هابط": "هبوط محتمل",
                            "عرضي أو غير محسوم": "محايد"}[scenario["trend"]]
                    st.subheader(bias)
                    st.selectbox("السيناريو على الشارت", ["صعود", "هبوط"],
                                 index=int(preferred == "هبوط"), key=direction_key)
                    trigger_side, invalidation_side = ("فوق", "تحت") if direction == "صعود" else ("تحت", "فوق")
                    confirmation, cancellation = st.columns(2)
                    confirmation.metric("مستوى التأكيد", f"{setup['trigger']:,.2f}")
                    cancellation.metric("مستوى الإلغاء", f"{setup['invalidation']:,.2f}")
                    st.caption(f"إغلاق شمعة {trigger_side} مستوى التأكيد أو {invalidation_side} مستوى الإلغاء.")
                    st.write(scenario["reason"])
                    if scenario["volume_ratio"] is not None:
                        st.caption(f"حجم الشمعة المرجعية ÷ متوسط 20 شمعة سابقة · {scenario['volume_ratio']:.2f}")
                    st.write(f"**{direction} · {tracking['state']}** · {tracking['reason']}")
                    if tracking["at"]:
                        st.caption(f"بداية شمعة تغيّر الحالة · {tracking['at']}")
                    for index, target in enumerate(tracking["targets"], 1):
                        status = (f"تحقق خلال الشمعة التي بدأت {target['reached_at']}"
                                  if target["reached_at"] else "لم يُرصد تحققه")
                        st.write(f"الهدف {index} · {target['price']:,.2f} {currency} · {status}")
                    st.caption("المتابعة لمدة 20 شمعة مكتملة. الأهداف تُرصد باللمس بعد شمعة التأكيد. "
                               "للشمعة التي تلغي السيناريو أولوية عند غموض ترتيب الحركة.")
                    if scenario["news"]:
                        with st.expander("الأخبار والعوامل المحتملة"):
                            for article in scenario["news"]:
                                st.text(f"{article['title']} · {article['tone']}")
                                st.caption(f"{article['source']} · {article['published']}")
                                url = article["url"]
                                if isinstance(url, str) and url.startswith(("https://", "http://")):
                                    st.link_button("فتح الخبر", url)
                    else:
                        st.caption("لا تتوفر أخبار مؤرخة من مزود السهم خلال الأيام السبعة السابقة لوقت التحليل.")
                    support, resistance = zones["support"], zones["resistance"]
                    st.write(f"**الدعم** {support[0]:,.2f}–{support[1]:,.2f}  ·  "
                             f"**المقاومة** {resistance[0]:,.2f}–{resistance[1]:,.2f}")
                    st.write(f"إغلاق فوق **{resistance[1]:,.2f}** يدعم سيناريو الصعود. "
                             f"إغلاق تحت **{support[0]:,.2f}** يدعم سيناريو الهبوط.")
                    st.caption(f"المستويات محسوبة حتى {scenario['as_of']}. اضغط زر التحليل لإعادة حسابها.")
                    if explanation:
                        st.write(explanation)
                    else:
                        st.caption("الشرح بالذكاء الاصطناعي غير متاح الآن. المستويات أعلاه محسوبة من الشموع.")
            match = next((row for row in results if row["symbol"] == detail_symbol), None)
            if match:
                with st.expander("إشارة الماسح وخطة الصفقة"):
                    levels = st.columns(4)
                    levels[0].metric("إشارة الماسح", match["signal"])
                    levels[1].metric("دخول مرجعي", f"{match['entry']:,.2f}")
                    levels[2].metric("وقف الخسارة", f"{match['stop']:,.2f}")
                    levels[3].metric("الهدف", f"{match['target']:,.2f}")
            with st.expander("آخر 15 شمعة والمؤشرات"):
                st.dataframe(display_frame.tail(15), width="stretch")

        show_stock_chart()

tool_options = list(dict.fromkeys(([detail_symbol] if detail_symbol else []) + analysis_options))

with plan_tab:
    st.subheader("خطة الصفقة وإدارة المخاطر")
    st.caption("القيم الافتراضية من إعدادات الماسح وإدارة المخاطر. مستويات سيناريو الاختراق تظهر في بطاقة الفرصة.")
    result_symbols = [r["symbol"] for r in results]
    sym = st.selectbox("السهم", list(dict.fromkeys(([detail_symbol] if detail_symbol else []) + result_symbols + analysis_options)), format_func=company_label, key="plan_sym")
    found = next((r for r in results if r["symbol"] == sym), None)
    p0 = found["price"] if found else 100.0
    e0 = found["entry"] if found else p0
    s0 = found["stop"] if found else p0 * .95
    t0 = found["target"] if found else p0 * 1.10
    plan_key = (sym, e0, s0, t0)
    a,b,c = st.columns(3)
    capital = a.number_input("رأس المال", min_value=0.0, value=10000.0, step=500.0)
    risk_pct = a.number_input("المخاطرة %", min_value=.1, max_value=5.0, value=1.0, step=.1)
    entry = b.number_input("سعر الدخول", min_value=.0001, value=max(float(e0),.0001), format="%.4f", key=f"entry-{plan_key}")
    stop = b.number_input("وقف الخسارة", min_value=.0001, value=max(float(s0),.0001), format="%.4f", key=f"stop-{plan_key}")
    target = c.number_input("الهدف", min_value=.0001, value=max(float(t0),.0001), format="%.4f", key=f"target-{plan_key}")
    allocation = c.number_input("حد التخصيص %", 1.0, 100.0, 20.0)
    plan = position_size(capital, risk_pct, entry, stop, allocation)
    if plan["valid"]:
        m = st.columns(4)
        m[0].metric("الكمية التقديرية", f"{plan['quantity']:,}")
        m[1].metric("قيمة الصفقة", f"{plan['notional']:,.2f}")
        m[2].metric("الخسارة المخططة", f"{plan['risk_amount']:,.2f}")
        m[3].metric("الربح عند الهدف", f"{plan['quantity']*max(0,target-entry):,.2f}")
        st.metric("العائد إلى المخاطرة", f"{(target-entry)/(entry-stop):.2f}" if target > entry else "الهدف أقل من الدخول")
    else:
        st.warning("تحقق من أن الدخول أعلى من وقف الخسارة.")

with portfolio_tab:
    st.subheader("المحفظة وسجل الصفقات")
    with st.form("add_trade_form", clear_on_submit=True):
        c1,c2,c3 = st.columns(3)
        mkt = c1.selectbox("السوق", ["الأمريكي","السعودي"])
        trade_symbol = c1.text_input("رمز السهم").strip().upper()
        side = c2.selectbox("نوع العملية", ["شراء","بيع","توزيعات","رسوم"])
        qty = c2.number_input("الكمية", min_value=0.0, value=0.0)
        price = c3.number_input("السعر", min_value=0.0, value=0.0)
        fees = c3.number_input("الرسوم", min_value=0.0, value=0.0)
        notes = st.text_input("ملاحظات")
        submitted = st.form_submit_button("حفظ العملية")
        if submitted:
            if trade_symbol and qty >= 0 and price >= 0:
                add_trade(mkt, trade_symbol, side, qty, price, fees, notes)
                st.success("تم حفظ العملية في قاعدة البيانات المحلية.")
            else:
                st.error("أدخل رمزاً صحيحاً.")
    trades = get_trades()
    if not trades.empty:
        st.dataframe(trades, width="stretch", hide_index=True)
        st.download_button("تنزيل سجل المحفظة CSV", trades.to_csv(index=False).encode("utf-8-sig"),
                           "nama_portfolio.csv", "text/csv")
        if st.button("مسح سجل الصفقات"):
            clear_trades()
            st.rerun()
    else:
        st.info("لا توجد صفقات مسجلة حتى الآن.")
    st.caption("قاعدة SQLite محلية. في Streamlit Cloud قد لا تكون الملفات المحلية دائمة عند إعادة نشر التطبيق؛ احتفظ بنسخة CSV أو اربط قاعدة بيانات خارجية لاحقاً.")

with backtest_tab:
    st.subheader("الاختبار التاريخي")
    bt_sym = st.selectbox("رمز الاختبار", tool_options, format_func=company_label, key="bt_sym")
    bt_strategy = st.selectbox("استراتيجية الاختبار", list(STRATEGIES), format_func=lambda x: STRATEGIES[x])
    bt_period = st.selectbox("فترة الاختبار", ["1y","2y","5y"], index=2)
    bt_interval = st.selectbox("فاصل الاختبار", ["1d","1wk"], index=0)
    horizon = st.slider("أقصى مدة احتفاظ بالشموع", 2, 60, 15)
    bt_threshold = st.slider("حد الإشارة للاختبار", 50, 95, 70)
    bt_key = (bt_sym, bt_strategy, bt_period, bt_interval, horizon, bt_threshold, fee_pct, slippage_pct)
    if st.button("تشغيل الاختبار التاريخي", disabled=bt_sym is None):
        st.session_state.pop("bt_output", None)
        with st.spinner("جارٍ تحميل البيانات وتشغيل الاختبار..."):
            raw = get_history(bt_sym, bt_period, bt_interval)
            if len(raw) < 61:
                st.session_state.bt_output = (bt_key, None, None)
            else:
                trades, stats = run_backtest(raw, bt_strategy, bt_threshold, horizon, fee_pct, slippage_pct)
                st.session_state.bt_output = (bt_key, trades, stats)
    if st.session_state.get("bt_output") and st.session_state.bt_output[0] == bt_key:
        _, trades, stats = st.session_state.bt_output
        if trades is None:
            st.warning("البيانات غير متاحة أو أقل من 61 شمعة. جرّب فترة أطول أو فاصلًا أقصر.")
        else:
            cols = st.columns(3)
            cols[0].metric("عدد الصفقات", stats["trades"])
            cols[1].metric("نسبة الفوز", f"{stats['win_rate_pct']}%")
            cols[2].metric("صافي العائد", f"{stats['net_return_pct']}%")
            cols = st.columns(3)
            cols[0].metric("أقصى تراجع", f"{stats['max_drawdown_pct']}%")
            cols[1].metric("Profit Factor", str(stats["profit_factor"]))
            cols[2].metric("Expectancy", f"{stats['expectancy_pct']}%")
            if not trades.empty:
                st.dataframe(trades, width="stretch", hide_index=True)
                st.download_button("تنزيل صفقات الاختبار CSV", trades.to_csv(index=False).encode("utf-8-sig"),
                                   "nama_backtest.csv", "text/csv")
            else:
                st.warning("لم ينتج عن هذه الإعدادات أي صفقات.")
    st.caption("الإشارة بعد إغلاق الشمعة والدخول في افتتاح الشمعة التالية. عند لمس الوقف والهدف في الشمعة نفسها يُفترض الوقف أولاً. الاختبار لا يضمن الأداء المستقبلي.")

with news_tab:
    st.subheader("الأخبار والبيانات الأساسية")
    news_sym = st.selectbox("السهم", tool_options, format_func=company_label, key="news_sym")
    if st.button("تحميل الأخبار والأساسيات", disabled=news_sym is None):
        info, news = get_fundamentals_news(news_sym)
        st.session_state.news_data = (news_sym, info, news)
    if st.session_state.get("news_data") and st.session_state.news_data[0] == news_sym:
        _, info, news = st.session_state.news_data
        metrics = [
            ("القيمة السوقية", info.get("marketCap")), ("مكرر الربحية", info.get("trailingPE")),
            ("مكرر الربحية المتوقع", info.get("forwardPE")), ("نمو الإيرادات", info.get("revenueGrowth")),
            ("هامش الربح", info.get("profitMargins")), ("عائد التوزيعات", info.get("dividendYield"))
        ]
        cols = st.columns(3)
        for col,(label,val) in zip(cols,metrics):
            if isinstance(val,(int,float)) and label in ("نمو الإيرادات","هامش الربح","عائد التوزيعات"):
                val = f"{val*100:.2f}%"
            elif isinstance(val,(int,float)):
                val = f"{val:,.2f}"
            col.metric(label, str(val) if val is not None else "غير متاح")
        if news:
            for item in news:
                sentiment = classify_headline(item["title"])
                st.markdown(f"- [{item['title']}]({item['url']}) — {item['source']} — {sentiment}" if item["url"] else f"- {item['title']} — {item['source']} — {sentiment}")
        else:
            st.info("لم تتوفر أخبار لهذا الرمز من المصدر المجاني.")
        st.caption("تصنيف العناوين بالكلمات المفتاحية استدلال أولي وليس نموذج فهم لغوي أو توصية.")

with alerts_tab:
    st.subheader("التنبيهات")
    alerts = get_alerts()
    if not alerts.empty:
        st.dataframe(alerts, width="stretch", hide_index=True)
        st.download_button("تنزيل التنبيهات CSV", alerts.to_csv(index=False).encode("utf-8-sig"),
                           "nama_alerts.csv", "text/csv")
        if st.button("مسح التنبيهات"):
            clear_alerts()
            st.rerun()
    else:
        st.info("لا توجد تنبيهات بعد.")

with watch_tab:
    st.subheader("قائمة المراقبة")
    watch = get_watchlist()
    if watch.empty:
        st.info("احفظ سهمًا من شاشة الشارت ليظهر هنا.")
    else:
        saved_symbols = watch["symbol"].tolist()
        saved_symbol = st.selectbox("الأسهم المحفوظة", saved_symbols, format_func=company_label)
        st.button("فتح السهم في الشارت", on_click=st.session_state.__setitem__,
                  args=("open_watch_symbol", saved_symbol))
        st.dataframe(watch.rename(columns={"symbol": "الرمز", "market": "السوق",
                                        "added_at": "تاريخ الإضافة"}),
                     width="stretch", hide_index=True)
    st.caption("تُحفظ القائمة في قاعدة بيانات التطبيق المحلية.")

st.divider()
st.caption(f"NAMA AI Trader · {VERSION} — نظام تحليلي تعليمي. بيانات مجانية قد تكون متأخرة أو غير مكتملة. ليست توصية مالية أو ضماناً للربح. التداول الحقيقي الآلي غير مفعل.")