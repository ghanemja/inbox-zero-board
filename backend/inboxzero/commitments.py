"""Commitments ledger — the chief-of-staff layer (docs/learning-logic.md §8).

Reads promises/requests out of a message and tracks who owes whom, across channels.
Two directions:
  party='them'  they owe you   (you asked / they promised you)
  party='you'   you owe them    (they asked / you promised them)

Rules-first + deterministic (testable without Ollama). Gemma refines ambiguous cases
via the same extraction signals (`asked_for`, `request_type`) — hook marked below.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from . import store

REQUEST_RE = re.compile(
    r"\b(can you|could you|would you|please|can we get|need (?:this|it|them|the\b).*\bby\b|"
    r"by (?:eod|eow|tomorrow|monday|tuesday|wednesday|thursday|friday|next week)|waiting on)\b",
    re.I)
PROMISE_RE = re.compile(r"\b(i'?ll|i will|we'?ll|we will|let me|i can (?:send|get|have).*\bby\b|"
                        r"will (?:send|get|share|have) (?:it|this|you|the))\b", re.I)
DUE_RE = re.compile(r"\bby (eod|eow|tomorrow|today|monday|tuesday|wednesday|thursday|friday|"
                    r"next week|\w+ \d{1,2})\b", re.I)


def _id(email_id: str, party: str) -> str:
    return "cm_" + hashlib.sha1(f"{email_id}:{party}".encode()).hexdigest()[:12]


def detect(email: dict, me: str) -> dict | None:
    """Return a commitment dict (unsaved) or None. Pure rules."""
    body = email.get("body", "") or ""
    from_me = email.get("from_addr", "").lower() == me.lower()
    is_request = bool(REQUEST_RE.search(body))
    is_promise = bool(PROMISE_RE.search(body))
    if not (is_request or is_promise):
        return None

    if from_me:
        # you asked someone → they owe you;  you promised → you owe them
        party = "them" if is_request and not is_promise else "you"
        counterpart = email["to_addrs"][0] if email.get("to_addrs") else None
    else:
        # they asked you → you owe them
        party = "you"
        counterpart = email.get("from_addr")
    if not counterpart:
        return None

    due_m = DUE_RE.search(body)
    return {
        "id": _id(email["id"], party),
        "party": party,
        "counterpart": counterpart,
        "what": email.get("subject", "").strip() or body[:60],
        "channel": email.get("channel", "email"),
        "due": due_m.group(1) if due_m else None,
        "status": "open",
        "source_email": email["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    # GEMMA HOOK: when rules are uncertain, pass body + extracted.asked_for to Gemma
    #   to confirm party + summarize `what` in one clause. Schema-constrained, temp=0.


def ingest(conn, email: dict, me: str) -> dict | None:
    c = detect(email, me)
    if c:
        store.save_commitment(conn, c)
    return c


_DUE_WEIGHT = {"today": 0, "eod": 0, "tomorrow": 1, "eow": 3, "friday": 3, "next week": 6}


def sla(due: str | None, overdue_days: int = 0) -> tuple[str, str]:
    """Map a due hint + age to a (level, label) badge. Level: red|amber|ok."""
    if overdue_days > 0:
        return ("red", f"{overdue_days} day{'s' if overdue_days != 1 else ''} overdue")
    if not due:
        return ("ok", "tracked")
    w = _DUE_WEIGHT.get(due.lower(), 2)
    if w <= 0:
        return ("amber", "due today")
    if w <= 3:
        return ("amber", f"due {due}")
    return ("ok", f"by {due}")
