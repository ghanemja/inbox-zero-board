"""Compounding org-graph metrics — temporal trends, bus-factor, and relationship health.

docs/learning-logic.md §10. All metrics are BEHAVIORAL and self-directed. See the
ethics rule at the bottom: this module must never score emotional state, sentiment,
or character, and must never produce a signal usable to surveil a person.

Pure-Python + testable (scripts/test_learning.py). Unified identity lets the same
human across email/Slack/Jira collapse to one node before any metric is computed.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import store, profiles


def _parse(ts: str) -> datetime:
    d = datetime.fromisoformat(ts)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def weekly_series(conn, counterpart: str, now: datetime, weeks: int = 8) -> list[int]:
    """Two-way message counts per week, oldest→newest, for the trailing `weeks`."""
    buckets = [0] * weeks
    start = now - timedelta(weeks=weeks)
    for it in store.interactions_for(conn, counterpart):
        t = _parse(it["ts"])
        if t < start or t > now:
            continue
        wk = min(weeks - 1, (t - start).days // 7)
        buckets[wk] += 1
    return buckets


def trend(series: list[int]) -> str:
    recent = sum(series[-3:])
    prior = sum(series[-6:-3])
    if all(v == 0 for v in series[:-3]) and recent > 0:
        return "new"
    if recent >= prior * 1.4:
        return "rising"
    if recent <= prior * 0.6:
        return "fading"
    return "steady"


def dormant(series: list[int]) -> bool:
    return sum(series[-2:]) <= 2 and any(v >= 5 for v in series[:4])


def bus_factor(conn) -> list[dict]:
    """Domains owned by exactly one (influential) person — single points of failure."""
    owners: dict[str, list[str]] = {}
    for row in conn.execute("SELECT email_addr FROM contacts"):
        prof = store.get_contact(conn, row["email_addr"]) or {}
        for d, m in prof.get("domains", {}).items():
            if m.get("support", 0) >= profiles.DOMAIN_MIN_SUPPORT:
                owners.setdefault(d, []).append(row["email_addr"])
    return [{"domain": d, "who": ppl[0]} for d, ppl in owners.items() if len(ppl) == 1]


def health_signals(conn, me: str, now: datetime) -> list[dict]:
    """Behavioral relationship signals — opt-in, self-directed. NO emotion/character.

    Each signal: {kind, level, who, text}. Levels: red|amber|info.
    """
    out = []

    # 1) aging commitments (logistics, not feelings)
    for c in store.list_commitments(conn, "open"):
        if not c.get("due"):
            continue
        out.append({"kind": "commitment", "level": "amber", "who": c["counterpart"],
                    "text": (f"Waiting on {c['counterpart']}: \"{c['what']}\""
                             if c["party"] == "them" else
                             f"You owe {c['counterpart']}: \"{c['what']}\"")})

    # 2) dormant-but-important + reciprocity imbalance (counts only)
    for row in conn.execute("SELECT email_addr FROM contacts"):
        addr = row["email_addr"]
        prof = store.get_contact(conn, addr) or {}
        series = weekly_series(conn, addr, now)
        if dormant(series):
            out.append({"kind": "dormant", "level": "amber", "who": addr,
                        "text": f"{addr} has gone quiet — was an active contact."})
        sent, recv = prof.get("counts", {}).get("sent", 0), prof.get("counts", {}).get("recv", 0)
        if recv and sent / recv > 1.8:
            out.append({"kind": "reciprocity", "level": "info", "who": addr,
                        "text": f"You message {addr} more than they reply ({sent}↑ {recv}↓)."})

    # 3) bus-factor (org resilience, not a person judgement)
    for r in bus_factor(conn):
        out.append({"kind": "bus_factor", "level": "amber", "who": r["who"],
                    "text": f"{r['who']} is the sole owner of \"{r['domain']}\" — single point of failure."})
    return out


# ───────────────────────────────────────────────────────────────────────────
# ETHICS RULE (enforced by code review, not just convention):
#   ALLOWED   : message counts, timing/latency, reciprocity ratios, silence,
#               commitment aging, domain ownership. All derivable from metadata.
#   FORBIDDEN : sentiment/emotion/tone-affect scoring of a person, "engagement"
#               or "mood" labels, anything a manager could use to surveil reports,
#               and persisting any psychological judgement about an individual.
#   Health signals are OPT-IN, computed locally, never exported as scores, and
#   framed as logistics ("thread idle with open commitment"), never character.
# ───────────────────────────────────────────────────────────────────────────
