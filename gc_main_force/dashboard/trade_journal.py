"""Personal trade log stored in trader_memory.json."""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import streamlit as st

from dashboard.i18n import session_label, t
from dashboard.playbook import PLAYBOOK_RULES

TICK_SIZE = 0.10
MEMORY_NAME = "trader_memory.json"


def memory_path(root: Path) -> Path:
    return root / MEMORY_NAME


def empty_memory() -> dict[str, Any]:
    return {"trades": [], "stats": _empty_stats()}


def _empty_stats() -> dict[str, Any]:
    return {
        "total_trades": 0,
        "open_trades": 0,
        "win_rate": None,
        "win_rate_following_playbook": None,
        "win_rate_ignoring_playbook": None,
        "best_session": None,
        "best_rule": None,
    }


def load_memory(root: Path) -> dict[str, Any]:
    path = memory_path(root)
    if not path.exists():
        data = empty_memory()
        save_memory(root, data)
        return data
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_memory()
    trades = list(data.get("trades") or [])
    stats = compute_stats(trades)
    return {"trades": trades, "stats": stats}


def save_memory(root: Path, data: dict[str, Any]) -> None:
    path = memory_path(root)
    payload = {
        "trades": list(data.get("trades") or []),
        "stats": compute_stats(list(data.get("trades") or [])),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.stem}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    last_err: Exception | None = None
    for attempt in range(8):
        try:
            os.replace(tmp, path)
            return
        except OSError as exc:
            last_err = exc
            time.sleep(0.05 * (attempt + 1))
    if tmp.exists():
        tmp.unlink(missing_ok=True)
    if last_err:
        raise last_err


def pnl_ticks(direction: str, entry: float, exit_price: float) -> float:
    move = (exit_price - entry) / TICK_SIZE
    if direction == "short":
        move = -move
    return round(move, 1)


def compute_stats(trades: list[dict[str, Any]]) -> dict[str, Any]:
    closed = [row for row in trades if row.get("pnl_ticks") is not None]
    open_n = len(trades) - len(closed)

    def _rate(rows: list[dict[str, Any]]) -> float | None:
        if not rows:
            return None
        wins = sum(1 for row in rows if float(row["pnl_ticks"]) > 0)
        return wins / len(rows)

    by_session: dict[str, float] = {}
    by_rule: dict[int, float] = {}
    for row in closed:
        session = str(row.get("session") or "off_hours")
        by_session[session] = by_session.get(session, 0.0) + float(row["pnl_ticks"])
        rule_id = int(row.get("rule_used") or 0)
        by_rule[rule_id] = by_rule.get(rule_id, 0.0) + float(row["pnl_ticks"])

    best_session = max(by_session, key=by_session.get) if by_session else None
    best_rule = max(by_rule, key=by_rule.get) if by_rule else None
    followed = [row for row in closed if row.get("followed_playbook")]
    ignored = [row for row in closed if not row.get("followed_playbook")]
    return {
        "total_trades": len(closed),
        "open_trades": open_n,
        "win_rate": _rate(closed),
        "win_rate_following_playbook": _rate(followed),
        "win_rate_ignoring_playbook": _rate(ignored),
        "best_session": best_session,
        "best_rule": best_rule,
    }


def has_open_trade(trades: list[dict[str, Any]]) -> bool:
    return any(row.get("pnl_ticks") is None for row in trades)


def add_trade(root: Path, trade: dict[str, Any]) -> dict[str, Any]:
    data = load_memory(root)
    data["trades"].append(trade)
    save_memory(root, data)
    return data


def _fmt_rate(value: float | None) -> str:
    if value is None:
        return t("stats.none")
    return f"{value * 100:.0f}%"


def open_trade_button() -> None:
    if st.button(t("journal.open"), key="journal_open_btn", use_container_width=True):
        st.session_state["journal_form_open"] = True


def render_trade_form(root: Path, state: dict[str, Any]) -> None:
    if not st.session_state.get("journal_form_open"):
        return

    st.caption(t("journal.paused"))
    default_px = state.get("last_price")
    with st.form("manual_trade_form", clear_on_submit=True):
        direction_col, entry_col, exit_col = st.columns(3)
        with direction_col:
            direction = st.radio(
                t("journal.direction"),
                ["long", "short"],
                format_func=lambda code: t(f"journal.{code}"),
                horizontal=True,
            )
        with entry_col:
            entry = st.number_input(
                t("journal.entry"),
                value=float(default_px) if default_px is not None else 0.0,
                step=0.1,
                format="%.2f",
            )
        with exit_col:
            exit_price = st.number_input(
                t("journal.exit"),
                value=0.0,
                step=0.1,
                format="%.2f",
            )
        follow_col, rule_col = st.columns([1, 2])
        with follow_col:
            followed = st.checkbox(t("journal.followed"), value=True)
        with rule_col:
            rule_used = st.selectbox(
                t("journal.rule"),
                [rule["id"] for rule in PLAYBOOK_RULES],
                format_func=lambda rule_id: f"#{rule_id} · {t(f'pb.{rule_id}.title')}",
            )
        notes = st.text_area(t("journal.notes"), height=68)
        save_col, cancel_col = st.columns(2)
        save = save_col.form_submit_button(t("journal.save"))
        cancel = cancel_col.form_submit_button(t("journal.cancel"))

    if cancel:
        st.session_state["journal_form_open"] = False
        st.rerun()
    if not save:
        return
    if entry <= 0:
        st.error(t("journal.need_entry"))
        return

    closed = exit_price > 0
    trade = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "direction": direction,
        "entry_price": round(float(entry), 2),
        "exit_price": round(float(exit_price), 2) if closed else None,
        "pnl_ticks": pnl_ticks(direction, float(entry), float(exit_price)) if closed else None,
        "followed_playbook": bool(followed),
        "rule_used": int(rule_used),
        "notes": notes.strip(),
        "session": state.get("active_session") or "off_hours",
    }
    add_trade(root, trade)
    st.session_state["journal_form_open"] = False
    st.success(t("journal.saved"))
    st.rerun()


def render_stats(root: Path) -> None:
    data = load_memory(root)
    stats = data["stats"]
    trades = data["trades"]
    if not trades:
        st.info(t("journal.empty"))
        return

    c1, c2, c3 = st.columns(3)
    c1.metric(t("stats.total"), stats["total_trades"])
    c2.metric(t("stats.open"), stats["open_trades"])
    c3.metric(t("stats.wr"), _fmt_rate(stats["win_rate"]))
    c4, c5 = st.columns(2)
    c4.metric(t("stats.wr_yes"), _fmt_rate(stats["win_rate_following_playbook"]))
    c5.metric(t("stats.wr_no"), _fmt_rate(stats["win_rate_ignoring_playbook"]))

    session = stats.get("best_session")
    rule = stats.get("best_rule")
    st.write(
        f"**{t('stats.session')}:** "
        + (session_label(session) if session else t("stats.none"))
    )
    st.write(
        f"**{t('stats.rule')}:** "
        + (f"#{rule} · {t(f'pb.{rule}.title')}" if rule else t("stats.none"))
    )

    st.subheader(t("journal.recent"))
    rows = []
    for row in trades[-12:]:
        rows.append(
            {
                t("stats.when"): row.get("timestamp", ""),
                t("journal.direction"): t(f"journal.{row.get('direction', 'long')}"),
                t("journal.entry"): row.get("entry_price"),
                t("journal.exit"): row.get("exit_price") if row.get("exit_price") is not None else t("stats.none"),
                t("stats.pnl"): row.get("pnl_ticks") if row.get("pnl_ticks") is not None else t("stats.none"),
                t("journal.followed"): t("yes") if row.get("followed_playbook") else t("no"),
                t("journal.rule"): f"#{row.get('rule_used')}",
                t("log.session"): session_label(row.get("session")),
            }
        )
    st.dataframe(list(reversed(rows)), use_container_width=True, hide_index=True)
