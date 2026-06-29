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
    if not ts:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    ts = ts.strip().replace("Z", "+00:00")   # Graph uses 'Z'; py<3.11 fromisoformat rejects it
    try:
        d = datetime.fromisoformat(ts)
    except ValueError:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
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


def _median(xs: list[float]):
    if not xs:
        return None
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def relationship_metrics(conn, me: str, now: datetime, window_days: int = 90) -> dict:
    """One pass over email threads → per-contact two-sided responsiveness.

    Returns {addr: {your_latency_h, their_latency_h, reply_pairs, their_pairs,
                    response_rate, open_loops, open_loop_subjects}}.
    Thread-aware: pairs a reply to its trigger within a conversation_id. Behavioral
    metadata only (no sentiment) — honors the ethics rule below.
    """
    me_l = me.lower()
    start = now - timedelta(days=window_days)
    rows = conn.execute(
        "SELECT from_addr, subject, received, conversation_id, has_unsub FROM emails "
        "WHERE conversation_id IS NOT NULL AND conversation_id != '' "
        "ORDER BY conversation_id, received").fetchall()

    M: dict[str, dict] = {}

    def m(addr):
        return M.setdefault(addr, {"your": [], "their": [], "denom": 0, "num": 0,
                                   "open_loops": 0, "open_loop_subjects": []})

    # group by conversation_id
    threads: dict[str, list] = {}
    for r in rows:
        t = _parse(r["received"])
        if t < start or t > now:
            continue
        threads.setdefault(r["conversation_id"], []).append((t, r["from_addr"].lower(),
                                                              r["from_addr"], r["subject"], r["has_unsub"]))

    for conv, msgs in threads.items():
        msgs.sort(key=lambda x: x[0])
        pending_in: dict[str, datetime] = {}   # their msg awaiting your reply
        pending_out = None                      # your msg awaiting their reply
        for ts, frm_l, frm, subj, unsub in msgs:
            if frm_l == me_l:                   # you sent
                for addr, in_ts in list(pending_in.items()):
                    m(addr)["your"].append((ts - in_ts).total_seconds() / 3600)
                    m(addr)["num"] += 1
                    del pending_in[addr]
                pending_out = ts
            else:                               # they sent
                if not unsub:
                    m(frm)["denom"] += 1
                pending_in[frm] = ts
                if pending_out and ts > pending_out:
                    m(frm)["their"].append((ts - pending_out).total_seconds() / 3600)
                    pending_out = None
        # open loop: thread's last message is inbound from them, aged > 5 days
        last_ts, last_l, last_frm, last_subj, _ = msgs[-1]
        if last_l != me_l and (now - last_ts).days > 5:
            d = m(last_frm)
            d["open_loops"] += 1
            if len(d["open_loop_subjects"]) < 5:
                d["open_loop_subjects"].append(last_subj or "(no subject)")

    out = {}
    for addr, d in M.items():
        out[addr] = {
            "your_latency_h": _median(d["your"]), "reply_pairs": len(d["your"]),
            "their_latency_h": _median(d["their"]), "their_pairs": len(d["their"]),
            "response_rate": round(100 * d["num"] / d["denom"]) if d["denom"] else None,
            "open_loops": d["open_loops"], "open_loop_subjects": d["open_loop_subjects"],
        }
    return out


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
