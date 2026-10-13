"""Login gate. Credentials stay in .streamlit/secrets.toml, outside git."""

from __future__ import annotations

import hmac

import streamlit as st

from dashboard.i18n import t


def _expected() -> tuple[str, str] | None:
    try:
        auth = st.secrets["auth"]
        username = str(auth["username"])
        password = str(auth["password"])
    except Exception:
        return None
    if not username or not password:
        return None
    return username, password


def _same(given: str, expected: str) -> bool:
    return hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8"))


def require_login() -> None:
    if st.session_state.get("logged_in") is True:
        return
    if st.session_state.get("lang") not in ("pt", "en"):
        st.session_state["lang"] = "pt"

    st.markdown(
        "<style>[data-testid='stSidebar']{display:none}"
        "[data-testid='collapsedControl']{display:none}</style>",
        unsafe_allow_html=True,
    )
    st.pills(
        t("language"),
        ["pt", "en"],
        format_func=lambda code: t(f"lang.{code}"),
        selection_mode="single",
        key="lang",
        label_visibility="collapsed",
    )
    st.title("🔒 " + t("login.title"))
    st.markdown(t("login.subtitle"))

    creds = _expected()
    if creds is None:
        st.error(t("login.missing"))
        st.stop()

    expected_user, expected_pass = creds
    _left, center, _right = st.columns([1, 2, 1])
    with center:
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input(t("login.user"))
            password = st.text_input(t("login.password"), type="password")
            submitted = st.form_submit_button(
                t("login.enter"),
                type="primary",
                use_container_width=True,
            )
        if submitted:
            if _same(username, expected_user) and _same(password, expected_pass):
                st.session_state["logged_in"] = True
                st.rerun()
            st.error(t("login.bad"))
    st.stop()
