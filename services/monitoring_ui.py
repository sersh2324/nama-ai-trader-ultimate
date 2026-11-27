"""Streamlit controls for private scenario monitoring."""

import os
from datetime import datetime, timezone

import streamlit as st

from services import monitoring


def account_owner():
    try:
        configured = bool(st.secrets.get("auth", {}).get("redirect_uri"))
    except FileNotFoundError:
        configured = False
    if not configured:
        return None
    if not st.user.is_logged_in:
        st.sidebar.button("تسجيل الدخول", on_click=st.login)
        return None
    st.sidebar.button("تسجيل الخروج", on_click=st.logout)
    if not st.user.get("sub"):
        return None
    return monitoring.owner_key(st.user.get("iss", ""), st.user["sub"])


def save_scenario(owner, item):
    if owner:
        monitoring.save(owner, item)
    else:
        saved = st.session_state.setdefault("guest_scenarios", {})
        saved.setdefault(monitoring.scenario_id(item), (item, monitoring.initial_progress()))
    st.toast("حُفظ السيناريو بمستوياته الأصلية.")


def save_watch(owner, symbol, market):
    if owner:
        monitoring.save_watch(owner, symbol, market)
    else:
        watch = st.session_state.setdefault("guest_watch", {})
        watch.setdefault(symbol, (symbol, market, datetime.now(timezone.utc).isoformat(timespec="seconds")))
    st.toast("تم حفظ السهم في المراقبة.")


def watch_rows(owner):
    return monitoring.watch_rows(owner) if owner else list(st.session_state.get("guest_watch", {}).values())


def show_saved_scenarios(owner, *, active):
    @st.fragment(run_every="5m" if active else None)
    def render():
        st.subheader("السيناريوهات المحفوظة")
        if not owner:
            st.caption("المراقبة في وضع الضيف خاصة بهذه الجلسة. سجّل الدخول عند توفره للحفظ عبر الجلسات.")
        elif not os.getenv("NAMA_DATABASE_URL"):
            st.caption("الحفظ على الخادم الحالي. قد تُفقد البيانات عند إعادة نشره.")
        records = monitoring.records(owner) if owner else [
            (None, key, item, status)
            for key, (item, status) in st.session_state.get("guest_scenarios", {}).items()
        ]
        if not records:
            st.info("شغّل تحليل سهم واحفظ السيناريو الذي تريد متابعته.")
            return
        st.caption("يُفحص السيناريو عند فتح المراقبة ثم دوريًا أثناء عرضها.")
        events = []
        prices = {}
        for key, item_id, item, previous in sorted(records, key=lambda row: row[2]["saved_at"], reverse=True):
            if previous["state"] in monitoring.TERMINAL_STATES:
                status, issue = previous, None
            else:
                cache_key = (item["symbol"], item["period"], item["interval"], item["feed"])
                if cache_key not in prices:
                    prices[cache_key] = monitoring.load_prices(item)
                status, issue = monitoring.evaluate_saved(item, previous, prices[cache_key])
            if key:
                monitoring.write_progress(key, item_id, previous, status)
            else:
                st.session_state.guest_scenarios[item_id] = (item, status)
            events.extend((item["symbol"], event["kind"], event["at"]) for event in status["events"])
            setup = item["scenario"]["setups"][item["direction"]]
            with st.expander(f"{item['symbol']} · {item['direction']} · {item['interval']} · {status['state']}"):
                st.write(item["scenario"]["reason"])
                st.caption(f"مرجع التحليل {item['scenario']['as_of']} · المصدر "
                           f"{'Alpaca ' + item['feed'] if item['feed'] else 'Yahoo Finance'}")
                st.write(f"التأكيد {setup['trigger']:.2f} · الإلغاء {setup['invalidation']:.2f}")
                for index, target in enumerate(setup["targets"], 1):
                    st.write(f"الهدف {index} · {target:.2f}")
                if issue:
                    st.info(issue)
        if events:
            st.subheader("أحداث السيناريوهات")
            st.dataframe([{"السهم": symbol, "الحدث": kind, "الشمعة": at}
                          for symbol, kind, at in sorted(events, key=lambda row: row[2], reverse=True)],
                         hide_index=True, width="stretch")

    if active:
        render()
