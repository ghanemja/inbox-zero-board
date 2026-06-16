"""Layer 1 — deterministic classification on structured signals.

Free, 100% reproducible, fully explainable. Handles the easy majority so Gemma
only runs on the genuinely ambiguous middle. Returns None when it can't decide
confidently, deferring to Layer 2. See docs/learning-logic.md §2.

`me` is the user's own email address (the inbox owner).
"""
from __future__ import annotations

BULK_HINTS = ("noreply", "no-reply", "newsletter", "notifications", "donotreply", "mailer")


def classify(email: dict, me: str) -> dict | None:
    me = me.lower()
    to = [a.lower() for a in email.get("to_addrs", [])]
    cc = [a.lower() for a in email.get("cc_addrs", [])]
    frm = (email.get("from_addr") or "").lower()

    # bulk / list mail → awareness or archive, no ambiguity
    if email.get("has_unsub") or any(h in frm for h in BULK_HINTS):
        return _r("awareness", 0.95, "bulk/list mail (List-Unsubscribe or no-reply sender)")

    addressed = me in to
    only_cc = (me in cc) and not addressed

    # purely cc'd and not the only recipient → awareness
    if only_cc and len(to) >= 1:
        return _r("awareness", 0.9, f"cc'd, not in To (addressed to {len(to)} others)")

    # directly addressed and sole/primary recipient → likely needs you, but the
    # *action* still needs extraction → defer to Gemma rather than guess a task.
    if addressed and len(to) <= 2:
        return None  # let Layer 2 extract task/due and confirm todo vs awareness

    # everything else is ambiguous
    return None


def _r(board: str, conf: float, reason: str) -> dict:
    return {"board": board, "confidence": conf, "reasoning": reason, "layer": "rules",
            "task": None, "due": None, "project_key": None, "topics": []}
