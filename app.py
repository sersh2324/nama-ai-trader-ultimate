from datetime import datetime
import math
import pandas as pd
import streamlit as st

from services.market_data import get_history, get_history_batch, get_fundamentals_news, INTRADAY_PERIODS
from services.universe import discover
from services.scanner import analyze_symbol
from services.backtest import run_backtest
from services.risk_manager import position_size
from services.portfolio import (initialize, add_trade, get_trades, clear_trades,
                                add_alert, get_alerts, clear_alerts, add_watch, get_watchlist)
from services.symbols import US, SA, company_name
from strategies.rules import STRATEGIES
from services.news_engine import classify_headline

VERSION = "1.1.0"
st.set_page_config(page_title="NAMA AI Trader Ultimate", page_icon="📈", layout="wide")
initialize()

st.title("📈 NAMA AI Trader Ultimate")
st.caption(f"الإصدار {VERSION} | تحليل هجين للأسهم الأمريكية والسعودية | إشارات يدوية مع قابلية تنفيذ آلي مستقبلًا")

with st.sidebar:
    st.header("إعدادات السوق")
    market = st.radio("السوق", ["الأمريكي", "السعودي", "السوقان معًا"])
    style = st.selectbox("نمط التداول", ["مضاربة يومية", "سوينغ", "استثمار طويل الأجل"])
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

@st.cache_data(ttl=86400, show_spinner=False)
def load_universe(market_name):
    return discover(market_name)

with st.spinner('جارٍ تحميل دليل الأسهم...'):
    universe, discovery_warnings = load_universe(market)
options = sorted(universe)
query = st.text_input('بحث باسم الشركة أو الرمز', placeholder='أرامكو أو Apple أو AAPL أو 2222').strip().casefold()
matches = [s for s in options if query in s.casefold() or query in universe[s].casefold()] if query else options
visible = matches[:250]
if len(matches)>250:
    st.caption(f'تظهر 250 نتيجة من {len(matches)}؛ اكتب اسمًا أو رمزًا لتضييق البحث.')
selected = st.multiselect('الأسهم للتحليل اليدوي', visible, default=[], format_func=lambda s:f'{universe[s]} ({s})', max_selections=100)
manual = st.text_input('إضافة رموز أخرى (افصل بينها بفاصلة)', '')
symbols = list(dict.fromkeys(selected + [x.strip().upper() for x in manual.split(',') if x.strip()]))[:100]
auto_scan = st.checkbox('فحص تلقائي دون اختيار الأسهم', value=True)
scan_limit = st.select_slider('عدد الأسهم في دورة الفحص', options=[25,50,100,250,500,1000], value=50, disabled=not auto_scan)
scan_offset = st.number_input('بداية الدفعة للوصول إلى بقية السوق', min_value=0, max_value=max(0,len(options)-1), value=0, step=50, disabled=not auto_scan)
if discovery_warnings:
    with st.expander('ملاحظات دليل الأسهم'):
        for warning in discovery_warnings: st.warning(warning)

tabs = st.tabs(["لوحة السوق", "اكتشاف الفرص", "تحليل السهم", "خطة الصفقة", "المحفظة", "الاختبار التاريخي", "الأخبار والأساسيات", "التنبيهات"])

with tabs[0]:
    st.subheader("لوحة السوق")
    st.write(f"السوق: **{market}** | نمط التداول: **{style}** | الإطار: **{interval}**")
    st.info("مصادر البيانات المجانية قد تكون متأخرة أو محدودة. لا تُعامل الأسعار على أنها لحظية ما لم يؤكد مزود البيانات ذلك.")
    st.metric("الرموز المكتشفة", len(options))
    st.metric("الأسهم المختارة يدويًا", len(symbols))
    st.caption("ابدأ بفحص الفرص لعرض آخر النتائج ومؤشرات السوق.")

if "scan_results" not in st.session_state:
    st.session_state.scan_results = []
if "scan_frames" not in st.session_state:
    st.session_state.scan_frames = {}

with tabs[1]:
    st.subheader("ماسح الفرص")
    scan_symbols = options[int(scan_offset):int(scan_offset)+int(scan_limit)] if auto_scan else symbols
    if st.button('🔎 بدء فحص الفرص', type='primary', disabled=not scan_symbols):
        rows, frames, errors = [], {}, []
        bar = st.progress(0)
        for start in range(0,len(scan_symbols),15):
            batch=scan_symbols[start:start+15]
            histories,batch_errors=get_history_batch(batch,period,interval)
            errors.extend(batch_errors)
            for sym in batch:
                try:
                    result=analyze_symbol(sym,histories.get(sym),style,strategy_choice)
                    if result:
                        frames[sym]=result.pop('frame')
                        result['company']=universe.get(sym,company_name(sym))
                        rows.append(result)
                        if result['score']>=threshold:
                            add_alert(sym,result['score'],result['signal'],result['strategy'],'؛ '.join(result['reasons']))
                    elif sym in histories:
                        errors.append(f'{sym}: insufficient history')
                except Exception as exc:
                    errors.append(f'{sym}: {str(exc)[:120]}')
            bar.progress(min(1.0,(start+len(batch))/len(scan_symbols)))
        bar.empty()
        rows.sort(key=lambda r:r['score'],reverse=True)
        st.session_state.scan_results,st.session_state.scan_frames=rows,frames
        st.session_state.scan_time=datetime.now().strftime('%Y-%m-%d %H:%M')
        st.session_state.scan_count=len(scan_symbols)
        st.session_state.scan_failed=len(errors)
        if errors:
            with st.expander(f'ملاحظات جلب البيانات ({len(errors)})'):
                st.write('\n'.join(errors[:200]))
    results = st.session_state.scan_results
    if results:
        st.caption(f"آخر فحص: {st.session_state.get('scan_time','')} | المطلوب: {st.session_state.get('scan_count',0)} | ملاحظات: {st.session_state.get('scan_failed',0)}")
        table = pd.DataFrame([{k:v for k,v in r.items() if k not in ("reasons","strategy_key")} for r in results])
        st.dataframe(table, use_container_width=True, hide_index=True)
        cols = st.columns(3)
        cols[0].metric("الأسهم المفحوصة", len(results))
        cols[1].metric("إشارات شراء محتملة", sum(r["signal"] == "شراء محتمل" for r in results))
        cols[2].metric("متوسط التقييم", round(sum(r["score"] for r in results)/len(results),1))
        st.download_button("تنزيل النتائج CSV", table.to_csv(index=False).encode("utf-8-sig"),
                           "nama_scan_results.csv", "text/csv")
        st.write("**تفاصيل أسباب الإشارة**")
        for r in results[:10]:
            with st.expander(f"{r['company']} ({r['symbol']}) — {r['score']}/100 — {r['signal']}"):
                st.write("الاستراتيجية:", r["strategy"])
                st.write("الأسباب:", "؛ ".join(r["reasons"]) or "لا توجد أسباب مؤكدة")
                st.write(f"الدخول المرجعي: {r['entry']:.4f} | الوقف: {r['stop']:.4f} | الهدف: {r['target']:.4f}")
    else:
        st.info("لم يتم الفحص بعد.")

with tabs[2]:
    st.subheader("تحليل سهم بالتفصيل")
    sym = st.selectbox("السهم", symbols or options[:1], format_func=lambda s: f"{company_name(s)} ({s})", key="detail_sym")
    if st.button("تحميل التحليل"):
        raw = get_history(sym, period, interval)
        if raw.empty:
            st.warning("لم تتوفر بيانات لهذا الرمز والفاصل الزمني.")
        else:
            from services.indicators import add_indicators
            detail = add_indicators(raw)
            st.session_state.detail = (sym, detail)
    if st.session_state.get("detail") and st.session_state.detail[0] == sym:
        d = st.session_state.detail[1]
        last = d.iloc[-1]
        c = st.columns(4)
        c[0].metric("آخر إغلاق", f"{last['Close']:.4f}")
        c[1].metric("RSI", f"{last['RSI']:.2f}" if pd.notna(last["RSI"]) else "—")
        c[2].metric("ATR %", f"{last['ATR_Pct']:.2f}%" if pd.notna(last["ATR_Pct"]) else "—")
        c[3].metric("ADX", f"{last['ADX']:.2f}" if pd.notna(last["ADX"]) else "—")
        chart_cols = [x for x in ["Close","EMA20","EMA50","EMA200","BB_Upper","BB_Lower"] if x in d]
        st.line_chart(d[chart_cols].tail(250))
        st.dataframe(d.tail(15), use_container_width=True)

with tabs[3]:
    st.subheader("خطة الصفقة وإدارة المخاطر")
    results = st.session_state.scan_results
    result_symbols = [r["symbol"] for r in results]
    sym = st.selectbox("السهم", result_symbols or symbols or options[:1], key="plan_sym")
    found = next((r for r in results if r["symbol"] == sym), None)
    p0 = found["price"] if found else 100.0
    e0 = found["entry"] if found else p0
    s0 = found["stop"] if found else p0 * .95
    t0 = found["target"] if found else p0 * 1.10
    a,b,c = st.columns(3)
    capital = a.number_input("رأس المال", min_value=0.0, value=10000.0, step=500.0)
    risk_pct = a.number_input("المخاطرة %", min_value=.1, max_value=5.0, value=1.0, step=.1)
    entry = b.number_input("سعر الدخول", min_value=.0001, value=max(float(e0),.0001), format="%.4f")
    stop = b.number_input("وقف الخسارة", min_value=.0001, value=max(float(s0),.0001), format="%.4f")
    target = c.number_input("الهدف", min_value=.0001, value=max(float(t0),.0001), format="%.4f")
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

with tabs[4]:
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

with tabs[5]:
    st.subheader("الاختبار التاريخي")
    bt_sym = st.selectbox("رمز الاختبار", symbols or options[:1], key="bt_sym")
    bt_strategy = st.selectbox("استراتيجية الاختبار", list(STRATEGIES), format_func=lambda x: STRATEGIES[x])
    bt_period = st.selectbox("فترة الاختبار", ["1y","2y","5y"], index=2)
    bt_interval = st.selectbox("فاصل الاختبار", ["1d","1wk"], index=0)
    horizon = st.slider("أقصى مدة احتفاظ بالشموع", 2, 60, 15)
    bt_threshold = st.slider("حد الإشارة للاختبار", 50, 95, 70)
    if st.button("تشغيل الاختبار التاريخي"):
        with st.spinner("جارٍ تحميل البيانات وتشغيل الاختبار..."):
            raw = get_history(bt_sym, bt_period, bt_interval)
            trades, stats = run_backtest(raw, bt_strategy, bt_threshold, horizon, fee_pct, slippage_pct)
            st.session_state.bt_output = (bt_sym, bt_strategy, trades, stats)
    if st.session_state.get("bt_output"):
        ss, sk, trades, stats = st.session_state.bt_output
        if ss == bt_sym and sk == bt_strategy:
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

with tabs[6]:
    st.subheader("الأخبار والبيانات الأساسية")
    news_sym = st.selectbox("السهم", symbols or options[:1], key="news_sym")
    if st.button("تحميل الأخبار والأساسيات"):
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

with tabs[7]:
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
st.caption("NAMA AI Trader Ultimate — نظام تحليلي تعليمي. بيانات مجانية قد تكون متأخرة أو غير مكتملة. ليست توصية مالية أو ضماناً للربح. التداول الحقيقي الآلي غير مفعل.")
