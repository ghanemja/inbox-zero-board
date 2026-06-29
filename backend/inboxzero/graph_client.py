"""Outlook pull via Microsoft Graph (MSAL device-code auth).

Read-only (`Mail.Read`). The device-code flow needs no client secret and no
embedded browser — the user authorizes once in their own browser. This is the
ONLY network egress in the system; everything downstream is local.

Needs an app registration (see .env.example). Auth flow below is real; wire the
token cache to disk for production so re-auth isn't needed each run.
"""
from __future__ import annotations

import html
import re

import requests  # noqa: F401  (top-level so real pulls fail fast if uninstalled)

import os

from config import AZURE_CLIENT_ID, AZURE_TENANT_ID, GRAPH_SCOPES, TOKEN_CACHE

GRAPH = "https://graph.microsoft.com/v1.0"

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]*\n[ \t]*(\n[ \t]*)+")


def _to_text(content: str, content_type: str) -> str:
    """Plain text for the classifier. We ask Graph for text bodies, but strip
    HTML as a belt-and-suspenders fallback if a message comes back as HTML."""
    if content and content_type.lower() == "html":
        content = _TAG_RE.sub(" ", content)
    content = html.unescape(content or "").replace("\xa0", " ")
    return _WS_RE.sub("\n\n", content).strip()


def acquire_token() -> str:
    import msal

    cache = msal.SerializableTokenCache()
    if os.path.exists(TOKEN_CACHE):
        with open(TOKEN_CACHE) as f:
            cache.deserialize(f.read())

    app = msal.PublicClientApplication(
        AZURE_CLIENT_ID, authority=f"https://login.microsoftonline.com/{AZURE_TENANT_ID}",
        token_cache=cache,
    )

    # 1) try a cached account silently (uses the refresh token — no re-login)
    result = None
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(GRAPH_SCOPES, account=accounts[0])

    # 2) fall back to interactive device-code flow
    if not result:
        flow = app.initiate_device_flow(scopes=GRAPH_SCOPES)
        if "user_code" not in flow:
            raise RuntimeError(f"device flow failed: {flow.get('error_description')}")
        print(flow["message"])  # "To sign in, open ... and enter code ABCD"
        result = app.acquire_token_by_device_flow(flow)

    if cache.has_state_changed:
        with open(TOKEN_CACHE, "w") as f:
            f.write(cache.serialize())

    if "access_token" not in result:
        raise RuntimeError(f"auth failed: {result.get('error_description')}")
    return result["access_token"]


def fetch_messages(token: str, limit: int = 100) -> list[dict]:
    """Pull recent messages and normalize to the store's email shape."""
    headers = {"Authorization": f"Bearer {token}",
               # ask Graph to render bodies as plain text (cleaner for the classifier)
               "Prefer": 'outlook.body-content-type="text"'}
    params = {
        "$top": min(limit, 50),
        "$select": "id,from,toRecipients,ccRecipients,subject,body,receivedDateTime,"
                   "conversationId,internetMessageHeaders",
        "$orderby": "receivedDateTime desc",
    }
    out: list[dict] = []
    url = f"{GRAPH}/me/messages"
    while url and len(out) < limit:
        r = requests.get(url, headers=headers, params=params, timeout=60)
        r.raise_for_status()
        page = r.json()
        out.extend(_normalize(m) for m in page.get("value", []))
        url = page.get("@odata.nextLink")
        params = None  # nextLink already encodes them
    return out[:limit]


def _normalize(m: dict) -> dict:
    headers = {h["name"].lower(): h["value"] for h in (m.get("internetMessageHeaders") or [])}
    body = m.get("body", {}) or {}
    return {
        "id": m["id"],
        "from_addr": (m.get("from", {}).get("emailAddress", {}) or {}).get("address", ""),
        "to_addrs": [r["emailAddress"]["address"] for r in m.get("toRecipients", [])],
        "cc_addrs": [r["emailAddress"]["address"] for r in m.get("ccRecipients", [])],
        "subject": m.get("subject", ""),
        "body": _to_text(body.get("content", ""), body.get("contentType", "text")),
        "has_unsub": 1 if "list-unsubscribe" in headers else 0,
        "is_reply": 1 if (m.get("subject", "") or "").lower().startswith("re:") else 0,
        "received": m.get("receivedDateTime", ""),
        "conversation_id": m.get("conversationId", ""),
    }
