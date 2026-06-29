"""Manual-export connector — read mail from files YOU exported, fully offline.

No Graph, no IMAP, no network: you export your own mail through Outlook's normal
UI, point the tool at the files. Supports a folder of .eml files and .mbox archives.

How to export from Outlook for Mac (incl. New Outlook):
  - Select messages → drag them into a Finder folder → each becomes a .eml file.
  - Then: --source files --path /path/to/that/folder
Other tools (Apple Mail, Thunderbird, Google Takeout) export .mbox → point --path at the .mbox.

Reuses the same RFC-822 parsing as the IMAP path.
"""
from __future__ import annotations

import email
import mailbox
import os
from email.utils import parsedate_to_datetime

from .imap_client import _addrs, _body, _hdr


def _to_dict(msg, fallback_id: str) -> dict:
    try:
        received = parsedate_to_datetime(msg.get("Date")).isoformat()
    except Exception:
        received = ""
    subject = _hdr(msg, "Subject")
    refs = (msg.get("References", "") or "").split()
    conv = (refs[0].strip("<>") if refs else (msg.get("In-Reply-To", "") or "").strip("<>"))
    return {
        "id": _hdr(msg, "Message-ID") or fallback_id,
        "from_addr": (_addrs(msg, "From") or [""])[0],
        "to_addrs": _addrs(msg, "To"),
        "cc_addrs": _addrs(msg, "Cc"),
        "subject": subject,
        "body": (_body(msg) or "").strip()[:8000],
        "has_unsub": 1 if msg.get("List-Unsubscribe") else 0,
        "is_reply": 1 if (subject.lower().startswith("re:") or msg.get("In-Reply-To")) else 0,
        "received": received,
        "conversation_id": conv,
    }


def _iter_messages(path: str):
    if os.path.isdir(path):
        # walk subfolders too, so a top-level folder with inbox/ and sent/ both load
        for root, _dirs, names in os.walk(path):
            for name in names:
                if name.lower().endswith((".eml", ".txt")):
                    fp = os.path.join(root, name)
                    try:
                        with open(fp, "rb") as f:
                            yield email.message_from_bytes(f.read()), os.path.relpath(fp, path)
                    except Exception:
                        continue
    elif path.lower().endswith(".mbox") or os.path.isfile(path):
        box = mailbox.mbox(path)
        for i, msg in enumerate(box):
            yield msg, f"mbox-{i}"
    else:
        raise RuntimeError(f"--path not found: {path}")


def fetch_messages(limit: int = 100, since: str | None = None, path: str | None = None) -> list[dict]:
    if not path:
        raise RuntimeError("Pass --path to a folder of .eml files or an .mbox archive.")
    out = [_to_dict(msg, fid) for msg, fid in _iter_messages(os.path.expanduser(path))]
    if since:
        out = [e for e in out if e["received"] and e["received"][:10] >= since]
    out.sort(key=lambda e: e["received"], reverse=True)   # newest first
    return out[:limit]
