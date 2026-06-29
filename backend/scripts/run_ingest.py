#!/usr/bin/env python3
"""CLI entry — pull + classify.

  python scripts/run_ingest.py --source db --limit 50 --me you@acme.com
  python scripts/run_ingest.py --source outlook --limit 100 --me you@acme.com
  python scripts/run_ingest.py --source outlook-local --limit 200   # Windows desktop Outlook, no Azure

Use --no-gemma to run rules-only (no Ollama needed) for a quick smoke test.
For --source outlook-local, --me auto-detects the signed-in Outlook account.
"""
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from inboxzero import pipeline  # noqa: E402

DEFAULT_ME = "you@acme.com"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["db", "outlook", "outlook-local", "outlook-mac", "imap", "files"], default="db")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--me", default=os.getenv("ME", DEFAULT_ME))
    ap.add_argument("--path", help="for --source files: folder of .eml files, or a .mbox archive")
    ap.add_argument("--no-gemma", action="store_true")
    ap.add_argument("--days", type=int, help="only pull mail from the last N days (fast first-run scope)")
    ap.add_argument("--since", help="only pull mail on/after YYYY-MM-DD (overrides --days)")
    ap.add_argument("--backfill", action="store_true",
                    help="metadata-only history pass: build the graph/profiles without per-email Gemma")
    ap.add_argument("--reclassify", action="store_true", help="re-run classification on already-seen mail")
    args = ap.parse_args()

    since = args.since
    if not since and args.days:
        since = (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime("%Y-%m-%d")

    # desktop Outlook / IMAP: auto-detect the account as `me`
    _autodetect = {"outlook-local": "inboxzero.outlook_local",
                   "outlook-mac": "inboxzero.outlook_mac", "imap": "inboxzero.imap_client"}
    if args.source in _autodetect and args.me == DEFAULT_ME:
        mod = __import__(_autodetect[args.source], fromlist=["current_user_smtp"])
        args.me = mod.current_user_smtp() or args.me
        print(f"Using account: {args.me}")

    if since:
        print(f"Scope: mail since {since}")
    counts = pipeline.run(args.me, source=args.source, limit=args.limit, use_gemma=not args.no_gemma,
                          since=since, reclassify=args.reclassify, backfill=args.backfill, path=args.path)
    print("Classified:")
    for board, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {board:14} {n}")


if __name__ == "__main__":
    main()
