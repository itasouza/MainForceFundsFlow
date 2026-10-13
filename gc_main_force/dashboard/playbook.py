"""Immutable manual-trading rules. Copy lives in dashboard/i18n.py."""

from __future__ import annotations

PLAYBOOK_RULES: list[dict] = [
    {"id": 1, "trigger": "always", "icon": "🧭"},
    {"id": 2, "trigger": "divergence_detected", "icon": "⚠️"},
    {"id": 3, "trigger": "price_near_absorption", "icon": "🎯"},
    {"id": 4, "trigger": "in_position", "icon": "🚪"},
    {"id": 5, "trigger": "off_session", "icon": "🕐"},
    {"id": 6, "trigger": "neutral_signal", "icon": "⛔"},
]

# Highest priority wins the header badge when several rules apply.
TRIGGER_PRIORITY = (
    "neutral_signal",
    "off_session",
    "divergence_detected",
    "price_near_absorption",
    "in_position",
    "always",
)

ABSORPTION_NEAR_TICKS = 20
OFF_SESSIONS = frozenset({"asian", "off_hours"})


def rule_by_id(rule_id: int) -> dict:
    for rule in PLAYBOOK_RULES:
        if rule["id"] == rule_id:
            return rule
    return PLAYBOOK_RULES[0]


def rule_by_trigger(trigger: str) -> dict:
    for rule in PLAYBOOK_RULES:
        if rule["trigger"] == trigger:
            return rule
    return PLAYBOOK_RULES[0]
