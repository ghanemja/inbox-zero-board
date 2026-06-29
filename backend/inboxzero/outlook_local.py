"""Local Outlook desktop connector (Windows, classic Outlook) via COM — NO Azure.

Reads mail straight from the already-signed-in Outlook app using pywin32. No app
registration, no cloud token, no network egress at all — the most local-first path.

Windows + classic Outlook desktop only. `pip install pywin32`. Bodies come back as
plain text already, so no HTML stripping is needed.

Mirrors graph_client's output shape so the rest of the pipeline is identical.
"""
from __future__ import annotations

OL_FOLDER_INBOX = 6   # olDefaultFolders.olFolderInbox
OL_TO, OL_CC = 1, 2   # olMailRecipientType
_UNSUB_PROP = ("http://schemas.microsoft.com/mapi/string/"
               "{00020386-0000-0000-C000-000000000046}/list-unsubscribe")


def _ns():
    import win32com.client  # Windows-only; imported lazily so the module loads anywhere
    return win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")


def current_user_smtp() -> str:
    """The signed-in account's email — used as `me` so 'from me' detection works."""
    try:
        ae = _ns().CurrentUser.AddressEntry
        ex = ae.GetExchangeUser()
        return (ex.PrimarySmtpAddress if ex else ae.Address) or ""
    except Exception:
        return ""


def _smtp_of(address_entry) -> str:
    """Resolve an Exchange DN (/O=...) to a real SMTP address; pass SMTP through."""
    try:
        ex = address_entry.GetExchangeUser()
        if ex and ex.PrimarySmtpAddress:
            return ex.PrimarySmtpAddress
    except Exception:
        pass
    try:
        return address_entry.Address or ""
    except Exception:
        return ""


def _sender_smtp(m) -> str:
    try:
        if getattr(m, "SenderEmailType", "") == "EX" and m.Sender is not None:
            return _smtp_of(m.Sender)
        return m.SenderEmailAddress or ""
    except Exception:
        return getattr(m, "SenderEmailAddress", "") or ""


def _recipients(m):
    to, cc = [], []
    try:
        for r in m.Recipients:
            addr = _smtp_of(r.AddressEntry) if getattr(r, "AddressEntry", None) else (r.Address or "")
            if not addr:
                continue
            (to if r.Type == OL_TO else cc if r.Type == OL_CC else to).append(addr)
    except Exception:
        pass
    return to, cc


def _received_iso(m) -> str:
    try:
        return m.ReceivedTime.strftime("%Y-%m-%dT%H:%M:%S")  # naive local; _parse treats as UTC
    except Exception:
        return ""


def _has_unsub(m) -> int:
    try:
        return 1 if m.PropertyAccessor.GetProperty(_UNSUB_PROP) else 0
    except Exception:
        return 0


def fetch_messages(limit: int = 100, since: str | None = None) -> list[dict]:
    inbox = _ns().GetDefaultFolder(OL_FOLDER_INBOX)
    items = inbox.Items
    items.Sort("[ReceivedTime]", True)  # newest first
    if since:  # 'YYYY-MM-DD' → Outlook Restrict (fast, server-side-ish) on received date
        from datetime import datetime
        d = datetime.strptime(since, "%Y-%m-%d")
        items = items.Restrict(f"[ReceivedTime] >= '{d.strftime('%m/%d/%Y')} 12:00 AM'")
    out: list[dict] = []
    for m in items:
        if len(out) >= limit:
            break
        try:
            if m.Class != 43:  # olMail; skip meeting requests, receipts, etc.
                continue
        except Exception:
            pass
        to, cc = _recipients(m)
        subject = getattr(m, "Subject", "") or ""
        out.append({
            "id": getattr(m, "EntryID", "") or f"local-{len(out)}",
            "from_addr": _sender_smtp(m),
            "to_addrs": to,
            "cc_addrs": cc,
            "subject": subject,
            "body": getattr(m, "Body", "") or "",   # already plain text
            "has_unsub": _has_unsub(m),
            "is_reply": 1 if subject.lower().startswith("re:") else 0,
            "received": _received_iso(m),
            "conversation_id": getattr(m, "ConversationID", "") or "",
        })
    return out
