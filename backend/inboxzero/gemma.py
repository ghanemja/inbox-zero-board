"""Layer 2 — local Gemma via Ollama. Deterministic, schema-constrained.

temp=0 + JSON schema (Ollama `format`) so output is reliable and parseable.
No data leaves the machine — Ollama is a local server. See docs/learning-logic.md §2.
"""
from __future__ import annotations

import json

from config import OLLAMA_HOST, GEMMA_MODEL, EMBED_MODEL

# Ollama supports a JSON schema in `format` to constrain decoding.
CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "board": {"type": "string", "enum": ["todo", "awareness", "project", "archive"]},
        "task": {"type": ["string", "null"]},
        "due": {"type": ["string", "null"]},
        "topics": {"type": "array", "items": {"type": "string"}},
        # profile-learning signals (feed profiles.observe → Delegate routing table)
        "request_type": {"type": ["string", "null"]},   # e.g. "catering request"
        "slots": {"type": "object"},                      # typed entities: date, headcount, budget_code...
        "asked_for": {"type": "array", "items": {"type": "string"}},  # slots the SENDER asked you to provide
        "reasoning": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["board", "reasoning", "confidence"],
}

PROMPT = """You triage one email for the inbox owner ({me}).
Decide the board:
- todo: the owner must personally do or reply to something. Extract the action as `task` and any deadline as `due`.
- awareness: FYI / cc'd / informational, no action needed.
- project: part of a multi-step initiative spanning weeks (e.g. a conference submission, a hire, a contract).
- archive: pure noise.
Also list 1-3 topics. If this email is a request of a recognizable type, set `request_type`
and pull any concrete details into `slots` (date, headcount, budget_code, dietary, location, etc).
If the SENDER is asking the owner to supply specific details, list those in `asked_for`.
Give a one-sentence `reasoning` and a 0-1 `confidence`. Never invent a deadline that isn't stated.

FROM: {frm}
TO: {to}
CC: {cc}
SUBJECT: {subject}
BODY:
{body}
"""


def health() -> tuple[bool, str]:
    """Is Ollama up and is the model present? Returns (ok, human message)."""
    import requests
    try:
        r = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        r.raise_for_status()
        models = [m.get("name", "") for m in r.json().get("models", [])]
    except Exception as e:
        return False, f"Ollama NOT reachable at {OLLAMA_HOST} ({e}). Start it: run 'ollama serve' (or open the Ollama app)."
    base = GEMMA_MODEL.split(":")[0]
    if GEMMA_MODEL not in models and not any(m.split(":")[0] == base for m in models):
        return False, (f"Ollama is running but model '{GEMMA_MODEL}' is not installed. "
                       f"Installed: {models or 'none'}. Run: ollama pull {GEMMA_MODEL}")
    return True, f"Ollama OK — model {GEMMA_MODEL} present."


def classify(email: dict, me: str) -> dict:
    import requests
    prompt = PROMPT.format(
        me=me, frm=email.get("from_addr", ""),
        to=", ".join(email.get("to_addrs", [])), cc=", ".join(email.get("cc_addrs", [])),
        subject=email.get("subject", ""), body=(email.get("body", "") or "")[:4000],
    )
    resp = requests.post(
        f"{OLLAMA_HOST}/api/generate",
        json={"model": GEMMA_MODEL, "prompt": prompt, "stream": False,
              "format": CLASSIFY_SCHEMA, "options": {"temperature": 0}},
        timeout=120,
    )
    resp.raise_for_status()
    data = json.loads(resp.json()["response"])
    data.setdefault("task", None)
    data.setdefault("due", None)
    data.setdefault("topics", [])
    data.setdefault("request_type", None)
    data.setdefault("slots", {})
    data.setdefault("asked_for", [])
    data["layer"] = "gemma"
    data["project_key"] = None  # set later by playbooks clustering
    return data


def embed(text: str) -> list[float] | None:
    """Local embedding (nomic-embed-text via Ollama) for fuzzy playbook matching.
    Returns None if the model/server is unavailable — callers fall back to exact match."""
    try:
        import requests
        resp = requests.post(
            f"{OLLAMA_HOST}/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": text},
            timeout=30,
        )
        resp.raise_for_status()
        vec = resp.json().get("embedding")
        return vec if vec else None
    except Exception:
        return None
