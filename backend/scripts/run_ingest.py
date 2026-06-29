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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from inboxzero import pipeline  # noqa: E402

DEFAULT_ME = "you@acme.com"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["db", "outlook", "outlook-local"], default="db")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--me", default=os.getenv("ME", DEFAULT_ME))
    ap.add_argument("--no-gemma", action="store_true")
    args = ap.parse_args()

    # local desktop Outlook: auto-detect the signed-in account as `me`
    if args.source == "outlook-local" and args.me == DEFAULT_ME:
        from inboxzero import outlook_local
        args.me = outlook_local.current_user_smtp() or args.me
        print(f"Using signed-in Outlook account: {args.me}")

    counts = pipeline.run(args.me, source=args.source, limit=args.limit, use_gemma=not args.no_gemma)
    print("Classified:")
    for board, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {board:14} {n}")


if __name__ == "__main__":
    main()
