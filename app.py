from datetime import datetime
import pandas as pd
import streamlit as st

from services.charts import price_chart
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

VERSION = "1.3.0-beta"
st.set_page_config(page_title="NAMA AI Trader Ultimate", page_icon="📈", layout="wide")
initialize()

st.markdown("""
<style>
.nama-banner {
    color: #f1f7fc;
    background: linear-gradient(110deg, #111f33, #163c42);
    border: 1px solid #40776e;
    border-radius: 16px;
    padding: clamp(16px, 3vw, 30px);
    margin-bottom: 1rem;
    text-align: right;
}
.nama-banner h1 { color: inherit; font-size: clamp(26px, 5vw, 42px); padding: 0; }
.nama-banner p { color: #cae3e5; margin: .45rem 0 0; }
</style>
<div class="nama-banner">
  <h1>NAMA AI Trader</h1>
  <p dir="rtl">تحليل الأسهم السعودية والأمريكية · تنفيذ الصفقات يدوي</p>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("إعدادات السوق")
    market = st.radio("السوق", ["الأمريكي", "السعودي", "السوقان معًا"], key="market")
    style = st.selectbox("نمط التداول", ["مضاربة يومية", "سوينغ", "استثمار طويل الأجل"], index=1)
    if style == "مضاربة يومية":
        interval = st.selectbox("الإطار الزمني", ["5m","15m","30m","60m"], index=1)
        period = st.selectbox("الفترة المتاحة", ["5d","30d","60d"], index=1)
    elif style == "سوينغ":
        interval = st.selectbox("الإطار الزمني", ["1h","1d","1wk"], index=1)
        period = st.selectbox("الفترة", ["6mo","1y","2y","5y"], index=2)
    else:
        interval = st.selectbox("الإطار الزمني", ["1d","1wk","1mo"], index=1)
        period = st.selectbox("الفترة", ["2y","5y","10y"], index=1)
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
with st.container(border=True):
    st.subheader("دليل الأسهم")
    if discovery_warnings:
        st.caption(f"{market} · {len(options):,} رمز متاح · قد تكون التغطية جزئية")
    else:
        st.caption(f"{market} · {len(options):,} رمز متاح")
    with st.expander("اختيار عدة أسهم للماسح أو إضافة رمز"):
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
    analysis_options = list(dict.fromkeys(picker_options + manual_symbols))
    detail_symbol = st.selectbox("بحث باسم الشركة أو الرمز", analysis_options,
                                 format_func=company_label, key="detail_sym",
                                 help="افتح القائمة واكتب اسم الشركة أو رمزها، ثم افتح تبويب تحليل السهم.")
if discovery_warnings:
    with st.expander('حالة تحميل دليل الشركات — مصادر بديلة أو أخطاء'):
        for warning in discovery_warnings:
            st.warning(warning)

navigation = st.tabs(["اكتشاف الفرص", "لوحة السوق", "تحليل السهم", "خطة الصفقة", "المحفظة", "الاختبار التاريخي", "الأخبار والأساسيات", "التنبيهات"])
market_tab, scanner_tab = navigation[1], navigation[0]

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
        st.caption(f'عدد الرموز المختارة يدويًا: {len(symbols)}')
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
            st.dataframe(table, use_container_width=True, hide_index=True)
            st.download_button("تنزيل النتائج CSV", table.to_csv(index=False).encode("utf-8-sig"),
                               "nama_scan_results.csv", "text/csv")

    else:
        if scan_completed:
            st.warning("انتهى الفحص دون نتائج قابلة للعرض. قد تكون الأسعار غير متاحة أو التاريخ غير كافٍ. جرّب 1d وسوينغ، وراجع ملاحظات البيانات.")
        else:
            st.info("لم يتم الفحص بعد.")

with navigation[2]:
    st.subheader(company_label(detail_symbol) if detail_symbol else "تحليل السهم")
    detail_key = (detail_symbol, period, interval)
    refresh = st.button("تحميل التحليل", disabled=detail_symbol is None, help="تحديث الأسعار والشارت.")
    detail_output = st.session_state.get("detail")
    if detail_symbol and (refresh or not detail_output or detail_output[0] != detail_key):
        with st.spinner("جارٍ جلب أسعار السهم..."):
            raw = get_history(detail_symbol, period, interval)
            st.session_state.detail = (detail_key, add_indicators(raw))
    if detail_symbol:
        d = st.session_state.detail[1]
        if d.empty:
            st.info("لم تتوفر أسعار لهذا الرمز والفاصل. غيّر الفترة أو اضغط تحميل التحليل للمحاولة مجددًا.")
        else:
            last = d.iloc[-1]
            currency = "SAR" if detail_symbol.endswith(".SR") else ("USD" if detail_symbol in universe else "")
            c = st.columns(4)
            c[0].metric("آخر إغلاق", f"{last['Close']:,.2f} {currency}".strip())
            c[1].metric("RSI", f"{last['RSI']:.2f}" if pd.notna(last["RSI"]) else "—")
            c[2].metric("ATR %", f"{last['ATR_Pct']:.2f}%" if pd.notna(last["ATR_Pct"]) else "—")
            c[3].metric("ADX", f"{last['ADX']:.2f}" if pd.notna(last["ADX"]) else "—")
            st.caption(f"آخر شمعة متاحة {d.index[-1]} · الفاصل {interval} · حتى 250 شمعة")
            ema = st.checkbox("المتوسطات المتحركة EMA", value=True)
            bands = st.checkbox("نطاقات بولينجر")
            overlays = []
            if ema:
                overlays.extend([("EMA20", "#e7ae55"), ("EMA50", "#6299ed"), ("EMA200", "#ac84ee")])
            if bands:
                overlays.extend([("BB_Upper", "#8e9caf"), ("BB_Lower", "#8e9caf")])
            st.plotly_chart(price_chart(d, overlays, currency), use_container_width=True,
                            config={"displaylogo": False, "scrollZoom": True}, key="price_chart")
            match = next((row for row in results if row["symbol"] == detail_symbol), None)
            if match:
                levels = st.columns(4)
                levels[0].metric("إشارة الماسح", match["signal"])
                levels[1].metric("دخول مرجعي", f"{match['entry']:,.2f}")
                levels[2].metric("وقف الخسارة", f"{match['stop']:,.2f}")
                levels[3].metric("الهدف", f"{match['target']:,.2f}")
            with st.expander("آخر 15 شمعة والمؤشرات"):
                st.dataframe(d.tail(15), use_container_width=True)

tool_options = list(dict.fromkeys(([detail_symbol] if detail_symbol else []) + analysis_options))

with navigation[3]:
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

with navigation[4]:
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
        st.dataframe(trades, use_container_width=True, hide_index=True)
        st.download_button("تنزيل سجل المحفظة CSV", trades.to_csv(index=False).encode("utf-8-sig"),
                           "nama_portfolio.csv", "text/csv")
        if st.button("مسح سجل الصفقات"):
            clear_trades()
            st.rerun()
    else:
        st.info("لا توجد صفقات مسجلة حتى الآن.")
    st.caption("قاعدة SQLite محلية. في Streamlit Cloud قد لا تكون الملفات المحلية دائمة عند إعادة نشر التطبيق؛ احتفظ بنسخة CSV أو اربط قاعدة بيانات خارجية لاحقاً.")

with navigation[5]:
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
                st.dataframe(trades, use_container_width=True, hide_index=True)
                st.download_button("تنزيل صفقات الاختبار CSV", trades.to_csv(index=False).encode("utf-8-sig"),
                                   "nama_backtest.csv", "text/csv")
            else:
                st.warning("لم ينتج عن هذه الإعدادات أي صفقات.")
    st.caption("الإشارة بعد إغلاق الشمعة والدخول في افتتاح الشمعة التالية. عند لمس الوقف والهدف في الشمعة نفسها يُفترض الوقف أولاً. الاختبار لا يضمن الأداء المستقبلي.")

with navigation[6]:
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

with navigation[7]:
    st.subheader("التنبيهات")
    alerts = get_alerts()
    if not alerts.empty:
        st.dataframe(alerts, use_container_width=True, hide_index=True)
        st.download_button("تنزيل التنبيهات CSV", alerts.to_csv(index=False).encode("utf-8-sig"),
                           "nama_alerts.csv", "text/csv")
        if st.button("مسح التنبيهات"):
            clear_alerts()
            st.rerun()
    else:
        st.info("لا توجد تنبيهات بعد.")
    watch = get_watchlist()
    st.write("قائمة المراقبة")
    if not watch.empty:
        st.dataframe(watch, use_container_width=True, hide_index=True)

st.divider()
st.caption(f"NAMA AI Trader · {VERSION} — نظام تحليلي تعليمي. بيانات مجانية قد تكون متأخرة أو غير مكتملة. ليست توصية مالية أو ضماناً للربح. التداول الحقيقي الآلي غير مفعل.")