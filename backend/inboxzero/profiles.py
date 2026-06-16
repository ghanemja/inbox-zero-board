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

from datetime import datetime, timezone

from . import store

REQUIRED_RATIO = 0.6
MIN_OBS = 2
DOMAIN_MIN_SUPPORT = 3


def blank_profile(addr: str, name: str = "", role: str = "") -> dict:
    return {"name": name, "role": role, "domains": {}, "request_templates": {},
            "counts": {"sent": 0, "recv": 0}}


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

    # --- domain accrual (§2) ---
    for topic in extracted.get("topics", []):
        d = prof["domains"].setdefault(topic, {"support": 0, "last_seen": now})
        d["support"] += 1
        d["last_seen"] = now
        d["confidence"] = min(1.0, d["support"] / 5)  # §6 conf()

    # --- request templates (§2 required-fields) ---
    rtype = extracted.get("request_type")
    if rtype:
        tpl = prof["request_templates"].setdefault(
            rtype, {"slots": {}, "tone_exemplars": [], "turnaround_samples": []})
        observed_slots = set(extracted.get("slots", {}).keys())
        # every slot we've ever seen for this type gets a `seen` tick; present ones get `present`
        known = set(tpl["slots"].keys()) | observed_slots
        for name in known:
            s = tpl["slots"].setdefault(name, {"seen": 0, "present": 0, "source": "recurring"})
            s["seen"] += 1
            if name in observed_slots:
                s["present"] += 1
        # "they asked you for X" → mark required immediately (strong signal)
        if not from_me:
            for name in extracted.get("asked_for", []):
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
