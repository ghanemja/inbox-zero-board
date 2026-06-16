"""Ingest loop — pull (or read) emails, classify, learn, persist.

Ties the layers together. Source 'db' reuses already-stored emails (e.g. the demo
seed); source 'outlook' pulls fresh via Graph.
"""
from __future__ import annotations

from . import store, classify, profiles


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
            counts[result["board"]] = counts.get(result["board"], 0) + 1

    return counts
