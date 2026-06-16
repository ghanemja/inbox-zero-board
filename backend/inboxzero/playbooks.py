"""Playbook learning + ticket replay — the Delegate brain (docs/learning-logic.md §3).

learn_from_sent_batch(): record each observed ticket→asks event and regeneralize
  the canonical subtask set (asks that recur across >=2 events).
replay(): given a new ticket, route each subtask to the owning contact and pre-fill
  the details, flagging anything missing.

Pure-Python and testable without Ollama (see scripts/test_learning.py). Optional
embedding-based fuzzy matching is left as a clearly-marked hook.
"""
from __future__ import annotations

import json

from . import store, profiles

MIN_EVENTS_FOR_CANONICAL = 2


def _key(goal_text: str) -> str:
    return goal_text.lower().replace("create ", "").strip()


def learn_from_sent_batch(conn, goal: str, sent_subtasks: list[dict]):
    """sent_subtasks: [{task, contact, domain, fields:[...]}] — one real delegation event."""
    key = _key(goal)
    row = conn.execute("SELECT spec FROM playbooks WHERE goal=?", (key,)).fetchone()
    spec = json.loads(row["spec"]) if row else {"learned": goal, "events": [], "support": 0}

    spec["events"].append(sent_subtasks)
    spec["support"] = len(spec["events"])
    spec["subtasks"] = _generalize(spec["events"])

    conn.execute("INSERT OR REPLACE INTO playbooks (goal, spec) VALUES (?,?)",
                 (key, json.dumps(spec)))


def _generalize(events: list[list[dict]]) -> list[dict]:
    """Keep asks that recur across >=MIN_EVENTS_FOR_CANONICAL events; union their fields."""
    counts: dict[str, dict] = {}
    for ev in events:
        for st in ev:
            c = counts.setdefault(st["task"], {"n": 0, "contact": st.get("contact"),
                                               "domain": st.get("domain"), "fields": set()})
            c["n"] += 1
            c["fields"].update(st.get("fields", []))
            if st.get("contact"):
                c["contact"] = st["contact"]
    threshold = MIN_EVENTS_FOR_CANONICAL if len(events) >= MIN_EVENTS_FOR_CANONICAL else 1
    return [{"task": t, "contact": c["contact"], "domain": c["domain"],
             "fields_needed": sorted(c["fields"])}
            for t, c in counts.items() if c["n"] >= threshold]


def replay(conn, goal_text: str, ticket_slots: dict, me: str) -> dict | None:
    spec = _match(conn, goal_text)
    if not spec:
        return None  # cold start (§5): caller falls back to Gemma decomposition

    out = []
    for st in spec["subtasks"]:
        contact = st.get("contact") or (_best_contact_for(conn, st["domain"]) if st.get("domain") else None)
        prof = store.get_contact(conn, contact) if contact else None
        need = list(st.get("fields_needed", []))
        # add any contact-template required fields not already listed
        if prof:
            for f in profiles.required_fields(prof, _key(goal_text)):
                if f not in need:
                    need.append(f)
        fields = {f: ticket_slots.get(f) for f in need}
        missing = [f for f in need if fields[f] is None]
        status = "needs_detail" if missing else ("ready" if contact else "needs_owner")
        out.append({"task": st["task"], "contact": contact, "fields": fields,
                    "missing": missing, "status": status,
                    "draft": _draft(prof, contact, st["task"], fields, missing)})
    return {"goal": _key(goal_text), "learned": spec.get("learned"),
            "support": spec.get("support", 0), "subtasks": out}


def _match(conn, goal_text: str) -> dict | None:
    row = conn.execute("SELECT spec FROM playbooks WHERE goal=?", (_key(goal_text),)).fetchone()
    if row:
        return json.loads(row["spec"])
    # OPTIONAL HOOK: embed goal_text (local nomic-embed via Ollama), nearest-neighbor
    #   against stored playbook centroids; return if cosine >= threshold. Skipped here
    #   to keep the core dependency-free; exact + normalized match covers the common case.
    return None


def _best_contact_for(conn, domain: str) -> str | None:
    best, best_support = None, 0
    for row in conn.execute("SELECT email_addr FROM contacts"):
        prof = store.get_contact(conn, row["email_addr"])
        m = (prof or {}).get("domains", {}).get(domain)
        if m and m["support"] > best_support:
            best, best_support = row["email_addr"], m["support"]
    return best


def _draft(prof, contact, task, fields, missing) -> str | None:
    if not contact:
        return None
    tone = (prof or {}).get("request_templates", {})
    opener = next((t["tone_exemplars"][0] for t in tone.values() if t.get("tone_exemplars")), None)
    filled = ", ".join(f"{k}: {v}" for k, v in fields.items() if v is not None)
    ask = f" Could you supply: {', '.join(missing)}?" if missing else ""
    lead = opener or f"Hi — re: {task.lower()}"
    return f"{lead} {filled}.{ask}".strip()
