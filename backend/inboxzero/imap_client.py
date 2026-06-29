"""Direct IMAP connector — works with Gmail (and any IMAP) without Outlook or Azure.

Read-only: opens the mailbox with readonly=True, so nothing is marked read or
modified. Mail is fetched from your provider (e.g. Gmail) — that's your own
mailbox serving you your own mail; classification stays 100% local afterward.

Gmail needs: IMAP enabled (Gmail → Settings → Forwarding and POP/IMAP) and an
**app password** (Google Account → Security → 2-Step Verification → App passwords).
Put creds in .env (IMAP_USER / IMAP_PASS). For Gmail, the native thread id
(X-GM-THRID) is used for project clustering.
"""
from __future__ import annotations

import email
import imaplib
import re
from email.utils import getaddresses, parsedate_to_datetime

from config import IMAP_HOST, IMAP_USER, IMAP_PASS

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_TAG_RE = re.compile(r"<[^>]+>")
_THRID_RE = re.compile(rb"X-GM-THRID (\d+)")


def _since_imap(since: str) -> str:
    y, m, d = since.split("-")
    return f"{int(d):02d}-{_MONTHS[int(m) - 1]}-{y}"   # IMAP wants DD-Mon-YYYY


def _hdr(msg, name: str) -> str:
    try:
        return str(email.header.make_header(email.header.decode_header(msg.get(name, "") or "")))
    except Exception:
        return msg.get(name, "") or ""


def _addrs(msg, name: str) -> list[str]:
    return [a for _, a in getaddresses([msg.get(name, "") or ""]) if a]


def _body(msg) -> str:
    def _dec(part):
        try:
            return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
        except Exception:
            return ""
    if msg.is_multipart():
        # prefer text/plain
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition", "")):
                return _dec(part)
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                return _TAG_RE.sub(" ", _dec(part))
        return ""
    text = _dec(msg)
    return _TAG_RE.sub(" ", text) if msg.get_content_type() == "text/html" else text


def current_user_smtp() -> str:
    return IMAP_USER


def fetch_messages(limit: int = 100, since: str | None = None) -> list[dict]:
    if not IMAP_USER or not IMAP_PASS:
        raise RuntimeError("Set IMAP_USER and IMAP_PASS in .env (Gmail: use an app password).")

    M = imaplib.IMAP4_SSL(IMAP_HOST)
    M.login(IMAP_USER, IMAP_PASS)
    try:
        M.select("INBOX", readonly=True)   # readonly → never modifies your mailbox
        crit = ["SINCE", _since_imap(since)] if since else ["ALL"]
        typ, data = M.search(None, *crit)
        ids = data[0].split()[-limit:]     # highest uids = newest
        gmail = "gmail" in IMAP_HOST.lower()
        spec = "(X-GM-THRID BODY.PEEK[])" if gmail else "(BODY.PEEK[])"

        out: list[dict] = []
        for num in reversed(ids):
            typ, msgdata = M.fetch(num, spec)
            if not msgdata or not isinstance(msgdata[0], tuple):
                continue
            prefix, raw = msgdata[0][0], msgdata[0][1]
            thrid = ""
            mt = _THRID_RE.search(prefix or b"")
            if mt:
                thrid = mt.group(1).decode()
            msg = email.message_from_bytes(raw)
            try:
                received = parsedate_to_datetime(msg.get("Date")).isoformat()
            except Exception:
                received = ""
            subject = _hdr(msg, "Subject")
            out.append({
                "id": _hdr(msg, "Message-ID") or f"imap-{num.decode()}",
                "from_addr": (_addrs(msg, "From") or [""])[0],
                "to_addrs": _addrs(msg, "To"),
                "cc_addrs": _addrs(msg, "Cc"),
                "subject": subject,
                "body": (_body(msg) or "").strip()[:8000],
                "has_unsub": 1 if msg.get("List-Unsubscribe") else 0,
                "is_reply": 1 if (subject.lower().startswith("re:") or msg.get("In-Reply-To")) else 0,
                "received": received,
                "conversation_id": thrid or (msg.get("In-Reply-To", "") or "").strip("<>"),
            })
        return out
    finally:
        try:
            M.logout()
        except Exception:
            pass
