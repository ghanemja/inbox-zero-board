"""Contact-profile learning — who handles what, and what details they need.

Implements docs/learning-logic.md §2 (signals) and §6 (update algorithm).
The profile is what the Delegate tab routes against. Pure-Python and testable
with synthetic `extracted` dicts (see scripts/test_learning.py) — no Ollama needed.

request_template structure (per contact, per request_type):
  {
    "slots": { name: {"seen": int, "present": int, "source": "recurring"|"they_asked"} },
    "tone_exemplars": [str],
    "turnaround_samples": [float]
  }
A slot is "required" when present/seen >= REQUIRED_RATIO over >= MIN_OBS observations,
or whenever source == "they_asked" (strong signal).
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone

from . import store

REQUIRED_RATIO = 0.6
MIN_OBS = 2
DOMAIN_MIN_SUPPORT = 3

_GREET_RE = re.compile(r"^\s*(hi there|hey there|dear|hello|hey|hi|good (?:morning|afternoon))\b", re.I)
_SIGNOFF_RE = re.compile(r"\b(best regards|warm regards|kind regards|best|cheers|thanks!?|thank you|regards|talk soon)\b[\s,!.-]*$", re.I)
_EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF☀-➿]")


def blank_profile(addr: str, name: str = "", role: str = "") -> dict:
    return {"name": name, "role": role, "domains": {}, "request_templates": {},
            "counts": {"sent": 0, "recv": 0, "solo": 0, "group": 0}, "style": _blank_style()}


def _blank_style() -> dict:
    return {"msgs": 0, "greet": {}, "signoff": {}, "len_words": [], "emoji": 0,
            "channel": {}, "turnaround_h": []}


def _update_style(prof: dict, email: dict):
    """Learn how YOU write to this person (from_me messages only). §2/§9."""
    st = prof.setdefault("style", _blank_style())
    body = (email.get("body", "") or "").strip()
    st["msgs"] += 1
    st["len_words"].append(len(body.split()))
    st["len_words"] = st["len_words"][-50:]
    if _EMOJI_RE.search(body):
        st["emoji"] += 1
    g = _GREET_RE.match(body)
    if g:
        st["greet"][g.group(1).title()] = st["greet"].get(g.group(1).title(), 0) + 1
    last_line = body.splitlines()[-1] if body.splitlines() else ""
    s = _SIGNOFF_RE.search(last_line)
    if s:
        st["signoff"][s.group(1).title()] = st["signoff"].get(s.group(1).title(), 0) + 1
    ch = email.get("channel", "email")
    st["channel"][ch] = st["channel"].get(ch, 0) + 1


def comm_style(prof: dict) -> dict:
    """Summarize the learned per-person communication style into a fingerprint."""
    st = prof.get("style") or _blank_style()
    n = max(1, st["msgs"])
    avg = sum(st["len_words"]) / len(st["len_words"]) if st["len_words"] else 0
    length = "short" if avg < 25 else "med" if avg < 70 else "long"
    top = lambda d: (Counter(d).most_common(1)[0][0] if d else None)
    counts = prof.get("counts", {})
    solo = counts.get("solo", 0)
    group = counts.get("group", 0)
    total = solo + group
    solo_pct = round(100 * solo / total) if total else None
    return {"greet": top(st["greet"]), "signoff": top(st["signoff"]),
            "len": length, "avg_words": round(avg),
            "emoji": st["emoji"] / n >= 0.3, "channel": top(st["channel"]) or "email",
            "samples": st["msgs"], "solo_pct": solo_pct}


def _first_sentence(body: str) -> str:
    body = (body or "").strip().replace("\n", " ")
    for sep in (". ", "! ", "? "):
        if sep in body:
            return body.split(sep)[0][:160]
    return body[:160]


def observe(conn, email: dict, me: str, extracted: dict):
    """Fold one email into the relevant contact profile (learning-logic §6)."""
    me_l = me.lower()
    from_me = (email.get("from_addr", "").lower() == me_l)
    other = email["from_addr"] if not from_me else (email["to_addrs"][0] if email.get("to_addrs") else None)
    if not other:
        return

    prof = store.get_contact(conn, other) or blank_profile(other)
    now = datetime.now(timezone.utc).isoformat()

    prof["counts"]["sent" if from_me else "recv"] += 1

    # --- 1:1 vs group tracking ---
    all_recipients = list(email.get("to_addrs") or []) + list(email.get("cc_addrs") or [])
    unique_others = [a for a in all_recipients if a.lower() != me_l]
    counts = prof["counts"]
    counts.setdefault("solo", 0)
    counts.setdefault("group", 0)
    if len(unique_others) <= 1:
        counts["solo"] += 1
    else:
        counts["group"] += 1

    # --- communication style: how YOU write to them (§2/§9) ---
    if from_me:
        _update_style(prof, email)

    # --- domain accrual (§2) ---
    for topic in (extracted.get("topics") or []):
        d = prof["domains"].setdefault(topic, {"support": 0, "last_seen": now})
        d["support"] += 1
        d["last_seen"] = now
        d["confidence"] = min(1.0, d["support"] / 5)  # §6 conf()

    # --- request templates (§2 required-fields) ---
    rtype = extracted.get("request_type")
    if rtype:
        tpl = prof["request_templates"].setdefault(
            rtype, {"slots": {}, "tone_exemplars": [], "turnaround_samples": []})
        observed_slots = set((extracted.get("slots") or {}).keys())
        # every slot we've ever seen for this type gets a `seen` tick; present ones get `present`
        known = set(tpl["slots"].keys()) | observed_slots
        for name in known:
            s = tpl["slots"].setdefault(name, {"seen": 0, "present": 0, "source": "recurring"})
            s["seen"] += 1
            if name in observed_slots:
                s["present"] += 1
        # "they asked you for X" → mark required immediately (strong signal)
        if not from_me:
            for name in (extracted.get("asked_for") or []):
                s = tpl["slots"].setdefault(name, {"seen": 1, "present": 0, "source": "they_asked"})
                s["source"] = "they_asked"
        # tone exemplar from your own outgoing asks
        if from_me:
            ex = _first_sentence(email.get("body", ""))
            if ex and ex not in tpl["tone_exemplars"]:
                tpl["tone_exemplars"] = (tpl["tone_exemplars"] + [ex])[-3:]

    store.save_contact(conn, other, prof)


def required_fields(prof: dict, request_type: str) -> list[str]:
    tpl = prof.get("request_templates", {}).get(request_type)
    if not tpl:
        return []
    out = []
    for name, s in tpl["slots"].items():
        if s.get("source") == "they_asked":
            out.append(name)
        elif s["seen"] >= MIN_OBS and s["present"] / s["seen"] >= REQUIRED_RATIO:
            out.append(name)
    return out


def owned_domains(conn, addr: str, min_support: int = DOMAIN_MIN_SUPPORT) -> list[str]:
    prof = store.get_contact(conn, addr)
    if not prof:
        return []
    return [d for d, m in prof["domains"].items() if m["support"] >= min_support]
