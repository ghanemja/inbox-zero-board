"""Outlook pull via Microsoft Graph (MSAL device-code auth).

Read-only (`Mail.Read`). The device-code flow needs no client secret and no
embedded browser — the user authorizes once in their own browser. This is the
ONLY network egress in the system; everything downstream is local.

Needs an app registration (see .env.example). Auth flow below is real; wire the
token cache to disk for production so re-auth isn't needed each run.
"""
from __future__ import annotations

import requests  # noqa: F401  (top-level so real pulls fail fast if uninstalled)

from config import AZURE_CLIENT_ID, AZURE_TENANT_ID, GRAPH_SCOPES

GRAPH = "https://graph.microsoft.com/v1.0"


def acquire_token() -> str:
    import msal

    app = msal.PublicClientApplication(
        AZURE_CLIENT_ID, authority=f"https://login.microsoftonline.com/{AZURE_TENANT_ID}"
    )
    flow = app.initiate_device_flow(scopes=GRAPH_SCOPES)
    if "user_code" not in flow:
        raise RuntimeError(f"device flow failed: {flow.get('error_description')}")
    print(flow["message"])  # "To sign in, use a web browser to open ... and enter code ABCD"
    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        raise RuntimeError(f"auth failed: {result.get('error_description')}")
    return result["access_token"]


def fetch_messages(token: str, limit: int = 100) -> list[dict]:
    """Pull recent messages and normalize to the store's email shape."""
    headers = {"Authorization": f"Bearer {token}"}
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
    return {
        "id": m["id"],
        "from_addr": (m.get("from", {}).get("emailAddress", {}) or {}).get("address", ""),
        "to_addrs": [r["emailAddress"]["address"] for r in m.get("toRecipients", [])],
        "cc_addrs": [r["emailAddress"]["address"] for r in m.get("ccRecipients", [])],
        "subject": m.get("subject", ""),
        "body": (m.get("body", {}) or {}).get("content", ""),
        "has_unsub": 1 if "list-unsubscribe" in headers else 0,
        "is_reply": 1 if (m.get("subject", "") or "").lower().startswith("re:") else 0,
        "received": m.get("receivedDateTime", ""),
    }
