#!/usr/bin/env python3
"""Load fake emails into the store so you can run the pipeline with no real inbox.

Mirrors the prototype's seed so the backend output lines up with the UI demo.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from inboxzero import store  # noqa: E402

ME = "you@acme.com"

SEED = [
    {"id": "e1", "from_addr": "sarah@acme.com", "to_addrs": [ME], "cc_addrs": [],
     "subject": "Please countersign — Acme NDA",
     "body": "Legal cleared the redlines. Attaching the final NDA for your signature; need it back before the Acme kickoff tomorrow.",
     "has_unsub": 0, "is_reply": 0, "received": "2026-06-14T09:00:00Z"},
    {"id": "e2", "from_addr": "tom@acme.com", "to_addrs": [ME], "cc_addrs": [],
     "subject": "Offsite travel — need your dates",
     "body": "Booking flights for the Q3 offsite. Send your preferred travel dates by end of week so I can lock fares.",
     "has_unsub": 0, "is_reply": 0, "received": "2026-06-14T10:00:00Z"},
    {"id": "e3", "from_addr": "deploy-bot@acme.com", "to_addrs": ["eng@acme.com"], "cc_addrs": [ME],
     "subject": "Eng deploy went out — v2.4",
     "body": "v2.4 is live in production. Changelog attached.",
     "has_unsub": 0, "is_reply": 0, "received": "2026-06-14T11:00:00Z"},
    {"id": "e4", "from_addr": "newsletter@industryweekly.com", "to_addrs": [ME], "cc_addrs": [],
     "subject": "This week in the industry",
     "body": "Top stories... unsubscribe any time.",
     "has_unsub": 1, "is_reply": 0, "received": "2026-06-14T07:00:00Z"},
    {"id": "e5", "from_addr": "facilities@acme.com", "to_addrs": ["all@acme.com"], "cc_addrs": [],
     "subject": "Office closed July 4",
     "body": "Reminder: the office is closed for the holiday. No action needed.",
     "has_unsub": 0, "is_reply": 0, "received": "2026-06-13T16:00:00Z"},
]


def main():
    store.init()
    with store.db() as conn:
        for e in SEED:
            store.upsert_email(conn, e)
    print(f"Seeded {len(SEED)} emails into {store.DB_PATH}. Owner = {ME}")
    print("Now run:  python scripts/run_ingest.py --source db --me you@acme.com --no-gemma")


if __name__ == "__main__":
    main()
