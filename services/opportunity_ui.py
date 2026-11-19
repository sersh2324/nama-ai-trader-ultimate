import json

import pandas as pd
import requests
import streamlit as st

from services.charts import price_chart
from services.market_data import get_history, get_option_chain, get_option_expirations
from services.opportunity_explanation import explain_opportunity
from services.opportunities import opportunity_levels, opportunity_status, option_quotes, tradingview_link


@st.cache_data(ttl=300, show_spinner=False)
def option_expirations(symbol):
    return get_option_expirations(symbol)


@st.cache_data(ttl=60, show_spinner=False)
def option_chain(symbol, expiration):
    return get_option_chain(symbol, expiration)


def show_options(symbol):
    if symbol.endswith(".SR"):
        st.caption("عرض عقود الخيارات متاح للرموز الأمريكية التي يغطيها مزوّد البيانات.")
        return

    with st.expander("عقود الخيارات الأمريكية"):
        if st.button("تحميل تواريخ العقود", key=f"load-options-{symbol}"):
            st.session_state["options_symbol"] = symbol
        if st.session_state.get("options_symbol") != symbol:
            return
        dates = option_expirations(symbol)
        if not dates:
            st.info("تعذر تحميل تواريخ الخيارات أو لا توجد عقود لهذا الرمز لدى المزوّد.")
            return
        expiration = st.selectbox("تاريخ الانتهاء", dates, key=f"expiry-{symbol}")
        side = st.radio("نوع العقد", ["شراء Call", "شراء Put"], horizontal=True, key=f"side-{symbol}")
        calls, puts = option_chain(symbol, expiration)
        table = calls if side == "شراء Call" else puts
        if table.empty:
            st.info("لا توجد أسعار عقود متاحة لهذا الاختيار.")
            return
        quotes = option_quotes(table).rename(columns={
            "contractSymbol": "رمز العقد", "strike": "سعر التنفيذ", "bid": "العرض",
            "ask": "الطلب", "lastTradeDate": "آخر صفقة بحسب المزوّد", "volume": "الحجم",
            "openInterest": "العقود المفتوحة", "impliedVolatility": "التقلب الضمني",
            "contractSize": "حجم العقد", "spread": "الفارق",
            "premium": "تكلفة العقد القياسي بالدولار",
        })
        st.caption("آخر صفقة تخص العقد وليست وقت تحديث العرض والطلب. تحقّق من السعر في سهم قبل اتخاذ القرار.")
        st.dataframe(quotes, hide_index=True, use_container_width=True)
        st.caption("لشراء عقد قياسي عند سعر الطلب، التكلفة المعروضة هي أقصى خسارة للعقد قبل الرسوم. مرور الوقت قد يقلّل من قيمة العقد.")


def show_opportunity(result, frame, period, interval):
    symbol = result["symbol"]
    levels = opportunity_levels(frame)
    if levels is None:
        st.info("الشموع المتاحة لا تكفي لرسم نطاق دخول صالح لهذا السيناريو.")
        return
    currency = "SAR" if symbol.endswith(".SR") else "USD"
    status = opportunity_status(result["price"], levels)
    with st.container(border=True):
        st.markdown(f"### {symbol} · {status}")
        st.caption(f"{interval} · {currency} · آخر شمعة لدى المزوّد {frame.index[-1]} · قد تكون البيانات متأخرة")
        st.write(f"**ليش ظهر؟** {'؛ '.join(result['reasons']) or 'لا توجد أسباب كافية من الاستراتيجية.'}")
        st.write(f"**وش ننتظر؟** إغلاق شمعة فوق {levels['trigger']:,.4f}. الشمعة الأخيرة قد تكون قيد التكوين.")
        st.write(f"**منطقة الدخول بعد التأكيد** · {levels['trigger']:,.4f}–{levels['entry_ceiling']:,.4f}")
        st.write(f"**إلغاء الفكرة** · {levels['invalidation']:,.4f} | **هدف السيناريو** · {levels['objective']:,.4f}")
        explanation_key = (symbol, interval, frame.index[-1], tuple(levels.items()), tuple(result["reasons"]))
        if st.button("اشرح الفرصة بالذكاء الاصطناعي", key=f"explain-{symbol}"):
            facts = {"symbol": symbol, "interval": interval, "status": status,
                     "reasons": result["reasons"], "levels": levels,
                     "condition": "إغلاق شمعة فوق مستوى التأكيد",
                     "latest_bar_may_be_incomplete": True}
            try:
                with st.spinner("جارٍ شرح السيناريو..."):
                    explanation = explain_opportunity(json.dumps(facts, ensure_ascii=False))
                if explanation:
                    st.session_state["opportunity_explanation"] = (explanation_key, explanation)
                else:
                    st.info("الشرح الأساسي ظاهر أعلاه. خدمة الشرح بالذكاء الاصطناعي تحتاج إعدادًا على الخادم.")
            except (requests.RequestException, KeyError, IndexError, ValueError):
                st.warning("تعذر جلب الشرح الإضافي. راجع أسباب الإشارة ومستوياتها أعلاه.")
        saved_explanation = st.session_state.get("opportunity_explanation")
        if saved_explanation and saved_explanation[0] == explanation_key:
            st.write(saved_explanation[1])

        title = f"{symbol} · {interval} · {currency} · {frame.index[-1]}"
        chart = price_chart(frame.tail(80), [], currency, levels=levels, title=title)
        st.plotly_chart(chart, use_container_width=True, key=f"opportunity-chart-{symbol}",
                        config={"displaylogo": False, "displayModeBar": True,
                                "toImageButtonOptions": {"format": "png", "filename": f"nama-{symbol}-{interval}"}})
        st.caption("اضغط أيقونة الكاميرا في الشارت لحفظ الصورة. للبحث في سهم، انسخ الرمز أدناه.")
        st.code(symbol.removesuffix(".SR"), language=None)
        st.link_button("فتح الشارت في TradingView", tradingview_link(symbol))

        watch_key = (symbol, interval, frame.index[-1], levels["trigger"])
        watches = st.session_state.setdefault("opportunity_watches", set())
        if watch_key not in watches:
            if st.button("تابع شرط التأكيد", key=f"watch-confirmation-{symbol}"):
                watches.add(watch_key)
                st.rerun()
        else:
            watch_confirmation(symbol, period, interval, frame.index[-1], levels)
        show_options(symbol)


@st.fragment(run_every="60s")
def watch_confirmation(symbol, period, interval, snapshot_time, levels):
    st.caption("نتحقق كل دقيقة أثناء فتح الجلسة. لاختبار السعر الآن، اضغط زر التحقق.")
    st.button("تحقق من الشرط", key=f"check-confirmation-{symbol}")
    fresh = get_history(symbol, period, interval)
    if fresh.empty:
        st.warning("تعذر تحديث الأسعار.")
        return

    cutoff = pd.Timestamp(snapshot_time)
    if fresh.index.tz is not None and cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize(fresh.index.tz)
    elif fresh.index.tz is None and cutoff.tzinfo is not None:
        cutoff = cutoff.tz_localize(None)

    completed = fresh.iloc[:-1]
    newer = completed.loc[completed.index > cutoff, "Close"]
    outcome = newer[(newer > levels["trigger"]) | (newer <= levels["invalidation"])]
    if newer.empty:
        st.info("ما وصلت شمعة مكتملة أحدث من شمعة الفرصة.")
    elif outcome.empty:
        st.info("لم يتحقق الشرط في الشموع الأحدث.")
    elif outcome.iloc[0] <= levels["invalidation"]:
        st.warning("أُلغيت الفكرة قبل التأكيد.")
    else:
        st.success(f"تحقق شرط الإغلاق في {outcome.index[0]} · {outcome.iloc[0]:,.4f}")
