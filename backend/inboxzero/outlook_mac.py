"""Local Outlook desktop connector (macOS, classic Outlook) via AppleScript — NO Azure.

The Mac twin of outlook_local.py: reads the inbox straight from the signed-in
Outlook for Mac app through osascript. No app registration, no cloud token.

Requires the **classic** Outlook for Mac (toggle "New Outlook" OFF — the new app's
AppleScript support is limited). Timestamps are emitted timezone-aware.

AppleScript over Outlook is slow per message, so this is best for a recent window
(--days N). For a big multi-year backfill on Mac, prefer the Graph path.
"""
from __future__ import annotations

import subprocess
from datetime import datetime, timedelta

FS = chr(31)  # unit separator between fields
RS = chr(30)  # record separator between messages


def _osascript(script: str) -> str:
    r = subprocess.run(["osascript", "-"], input=script, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise RuntimeError(f"osascript failed: {r.stderr.strip() or 'is classic Outlook for Mac open + signed in?'}")
    return r.stdout


def current_user_smtp() -> str:
    script = '''
    tell application "Microsoft Outlook"
      try
        return email address of (first exchange account)
      end try
      try
        return email address of (first imap account)
      end try
      try
        return email address of (first pop account)
      end try
      return ""
    end tell'''
    try:
        return _osascript(script).strip()
    except Exception:
        return ""


def _build(limit: int) -> str:
    # one line per message, fields joined by FS, records by RS. Date emitted as
    # seconds-from-local-1970 (locale-independent); Python attaches the local tz.
    return f'''
    on j(lst, d)
      set tid to AppleScript's text item delimiters
      set AppleScript's text item delimiters to d
      set s to lst as text
      set AppleScript's text item delimiters to tid
      return s
    end j
    tell application "Microsoft Outlook"
      set FS to (ASCII character 31)
      set RS to (ASCII character 30)
      set zero to (current date)
      set year of zero to 1970
      set month of zero to January
      set day of zero to 1
      set time of zero to 0
      set out to ""
      set msgs to messages of inbox
      set n to (count of msgs)
      if n > {int(limit)} then set n to {int(limit)}
      repeat with i from 1 to n
        set m to item i of msgs
        try
          set subj to subject of m
        on error
          set subj to ""
        end try
        set frm to ""
        try
          set frm to address of (sender of m)
        end try
        set toL to {{}}
        try
          repeat with r in (to recipients of m)
            try
              set end of toL to (address of (email address of r))
            end try
          end repeat
        end try
        set ccL to {{}}
        try
          repeat with r in (cc recipients of m)
            try
              set end of ccL to (address of (email address of r))
            end try
          end repeat
        end try
        set secs to ((time received of m) - zero)
        set mid to ""
        try
          set mid to (id of m) as text
        end try
        set conv to ""
        try
          set conv to (exchange conversation id of m) as text
        end try
        set body to ""
        try
          set body to plain text content of m
        end try
        try
          if (length of body) > 4000 then set body to text 1 thru 4000 of body
        end try
        set out to out & subj & FS & frm & FS & (my j(toL, ",")) & FS & (my j(ccL, ",")) & FS & (secs as text) & FS & mid & FS & conv & FS & body & RS
      end repeat
      return out
    end tell'''


def fetch_messages(limit: int = 100, since: str | None = None) -> list[dict]:
    raw = _osascript(_build(limit))
    out: list[dict] = []
    for rec in raw.split(RS):
        if not rec.strip():
            continue
        parts = rec.split(FS)
        if len(parts) < 8:
            continue
        subj, frm, to_s, cc_s, secs, mid, conv, body = parts[:8]
        try:  # local wall-clock -> tz-aware ISO (audit fix: never naive-as-UTC)
            received = (datetime(1970, 1, 1) + timedelta(seconds=float(secs))).astimezone().isoformat()
        except Exception:
            received = ""
        if since and received and received[:10] < since:
            continue
        out.append({
            "id": mid or f"mac-{len(out)}",
            "from_addr": frm,
            "to_addrs": [a for a in to_s.split(",") if a],
            "cc_addrs": [a for a in cc_s.split(",") if a],
            "subject": subj,
            "body": body,
            "has_unsub": 0,   # header not readily exposed via Mac AppleScript
            "is_reply": 1 if subj.lower().startswith("re:") else 0,
            "received": received,
            "conversation_id": conv,
        })
    return out[:limit]
