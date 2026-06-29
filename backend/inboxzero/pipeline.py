"""Ingest loop — pull (or read) emails, classify, learn, persist.

Incremental + idempotent: each email is processed exactly once (a classification
row marks it done), so scheduled re-runs are cheap and never double-count the graph.

Modes:
  normal   — classify (rules → Gemma → gate) + learn, only for emails not yet done.
  backfill — metadata-only: build the graph/profiles/commitments from history WITHOUT
             per-email Gemma (cheap over years of mail). Marked board='history'
             (hidden from the boards), so it enriches the relationship graph only.

Date scoping: `since='YYYY-MM-DD'` limits the pull to recent mail for fast first-run.
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import store, classify, profiles, commitments


def run(me: str, source: str = "db", limit: int = 100, use_gemma: bool = True,
        since: str | None = None, reclassify: bool = False, backfill: bool = False,
        path: str | None = None):
    store.init()
    with store.db() as conn:
        if source == "outlook":
            from . import graph_client  # lazy — only needs `requests`/`msal` for real pulls
            token = graph_client.acquire_token()
            for e in graph_client.fetch_messages(token, limit, since=since):
                store.upsert_email(conn, e)
        elif source == "outlook-local":
            from . import outlook_local  # lazy — Windows + pywin32 only
            for e in outlook_local.fetch_messages(limit, since=since):
                store.upsert_email(conn, e)
        elif source == "outlook-mac":
            from . import outlook_mac  # lazy — macOS + classic Outlook via AppleScript
            for e in outlook_mac.fetch_messages(limit, since=since):
                store.upsert_email(conn, e)
        elif source == "imap":
            from . import imap_client  # lazy — direct IMAP (Gmail / any), stdlib only
            for e in imap_client.fetch_messages(limit, since=since):
                store.upsert_email(conn, e)
        elif source == "files":
            from . import files_client  # lazy — manual export (.eml folder / .mbox), offline
            for e in files_client.fetch_messages(limit, since=since, path=path):
                store.upsert_email(conn, e)

        done = {r["email_id"] for r in conn.execute("SELECT email_id FROM classifications")}
        counts: dict[str, int] = {}
        for e in store.iter_emails(conn):
            already = e["id"] in done
            if already and not reclassify:
                counts["skipped"] = counts.get("skipped", 0) + 1
                continue

            result = _history_row(e) if backfill else classify.classify_email(e, me, use_gemma=use_gemma)
            store.save_classification(conn, result)
            if not already:  # learn from each email exactly once (keeps the graph honest)
                profiles.observe(conn, e, me, result if not backfill else {"topics": []})
                commitments.ingest(conn, e, me)
                _record_interaction(conn, e, me)
            counts[result["board"]] = counts.get(result["board"], 0) + 1

    return counts


def _history_row(e: dict) -> dict:
    """A 'done' marker for backfilled history mail — hidden from the boards."""
    return {"email_id": e["id"], "board": "history", "task": None, "due": None,
            "project_key": None, "topics": [], "reasoning": "history backfill",
            "layer": "backfill", "confidence": 1.0,
            "decided_at": datetime.now(timezone.utc).isoformat()}


def _record_interaction(conn, e: dict, me: str):
    from_me = e.get("from_addr", "").lower() == me.lower()
    other = (e["to_addrs"][0] if e.get("to_addrs") else None) if from_me else e.get("from_addr")
    if not other:
        return
    canonical = store.resolve_identity(conn, other)   # collapse cross-channel aliases
    store.record_interaction(conn, canonical, e.get("channel", "email"),
                             "out" if from_me else "in", e.get("received", ""))
