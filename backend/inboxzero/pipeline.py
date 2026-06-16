"""Ingest loop — pull (or read) emails, classify, learn, persist.

Ties the layers together. Source 'db' reuses already-stored emails (e.g. the demo
seed); source 'outlook' pulls fresh via Graph.
"""
from __future__ import annotations

from . import store, classify, profiles, commitments


def run(me: str, source: str = "db", limit: int = 100, use_gemma: bool = True):
    store.init()
    with store.db() as conn:
        if source == "outlook":
            from . import graph_client  # lazy — only needs `requests`/`msal` for real pulls
            token = graph_client.acquire_token()
            for e in graph_client.fetch_messages(token, limit):
                store.upsert_email(conn, e)

        emails = list(store.iter_emails(conn))[:limit]
        counts: dict[str, int] = {}
        for e in emails:
            result = classify.classify_email(e, me, use_gemma=use_gemma)
            store.save_classification(conn, result)
            profiles.observe(conn, e, me, result)
            commitments.ingest(conn, e, me)   # chief-of-staff: who owes whom
            _record_interaction(conn, e, me)  # compounding graph: temporal edge
            counts[result["board"]] = counts.get(result["board"], 0) + 1

    return counts


def _record_interaction(conn, e: dict, me: str):
    from_me = e.get("from_addr", "").lower() == me.lower()
    other = (e["to_addrs"][0] if e.get("to_addrs") else None) if from_me else e.get("from_addr")
    if not other:
        return
    canonical = store.resolve_identity(conn, other)   # collapse cross-channel aliases
    store.record_interaction(conn, canonical, e.get("channel", "email"),
                             "out" if from_me else "in", e.get("received", ""))
