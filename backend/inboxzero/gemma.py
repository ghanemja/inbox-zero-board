"""Layer 2 — local Gemma via Ollama. Deterministic, schema-constrained.

temp=0 + JSON schema (Ollama `format`) so output is reliable and parseable.
No data leaves the machine — Ollama is a local server. See docs/learning-logic.md §2.
"""
from __future__ import annotations

import json

from config import OLLAMA_HOST, GEMMA_MODEL, EMBED_MODEL, OLLAMA_TIMEOUT, OLLAMA_KEEP_ALIVE

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

Respond with ONLY a JSON object, no prose, with these keys:
{{"board": "todo|awareness|project|archive", "task": string|null, "due": string|null,
 "topics": [string], "request_type": string|null, "slots": {{}}, "asked_for": [string],
 "reasoning": string, "confidence": number}}

FROM: {frm}
TO: {to}
CC: {cc}
SUBJECT: {subject}
BODY:
{body}
"""


_RESOLVED_MODEL: str | None = None


def _installed_models() -> list[str]:
    import requests
    r = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
    r.raise_for_status()
    return [m.get("name", "") for m in r.json().get("models", [])]


def resolve_model() -> str:
    """Use GEMMA_MODEL if installed; else auto-pick any installed gemma (or any chat
    model). Means it 'just works' with whatever you've pulled, no .env edit needed."""
    global _RESOLVED_MODEL
    if _RESOLVED_MODEL:
        return _RESOLVED_MODEL
    try:
        models = _installed_models()
    except Exception:
        return GEMMA_MODEL
    if GEMMA_MODEL in models:
        _RESOLVED_MODEL = GEMMA_MODEL
    else:
        chat = [m for m in models if "embed" not in m.lower()]
        gemma = [m for m in chat if "gemma" in m.lower()]
        _RESOLVED_MODEL = (gemma or chat or [GEMMA_MODEL])[0]
    return _RESOLVED_MODEL


def health() -> tuple[bool, str]:
    """Is Ollama up and is a usable model present? Returns (ok, human message)."""
    try:
        models = _installed_models()
    except Exception as e:
        return False, f"Ollama NOT reachable at {OLLAMA_HOST} ({e}). Start it: run 'ollama serve' (or open the Ollama app)."
    if not [m for m in models if "embed" not in m.lower()]:
        return False, f"Ollama is running but no chat model is installed. Run: ollama pull {GEMMA_MODEL}"
    model = resolve_model()
    note = "" if model == GEMMA_MODEL else f" (GEMMA_MODEL='{GEMMA_MODEL}' not found — using this instead)"
    return True, f"Ollama OK — using model '{model}'{note}."


def warmup() -> tuple[bool, str]:
    """Load the model into memory once (first call is the slow one). Returns (ok, msg)."""
    import time
    import requests
    try:
        t = time.time()
        r = requests.post(f"{OLLAMA_HOST}/api/generate",
                          json={"model": resolve_model(), "prompt": "ok", "stream": False,
                                "keep_alive": OLLAMA_KEEP_ALIVE, "options": {"num_predict": 1}},
                          timeout=OLLAMA_TIMEOUT)
        r.raise_for_status()
        return True, f"model warm ({time.time() - t:.0f}s to load)"
    except Exception as e:
        return False, f"warmup failed ({e})"


def _parse_json(text: str) -> dict:
    """Tolerant: parse the model's response, or recover the first {...} object."""
    text = (text or "").strip()
    try:
        return json.loads(text)
    except Exception:
        i, j = text.find("{"), text.rfind("}")
        if i != -1 and j > i:
            try:
                return json.loads(text[i:j + 1])
            except Exception:
                pass
    raise ValueError(f"unparseable model output: {text[:120]!r}")


def classify(email: dict, me: str) -> dict:
    import requests
    prompt = PROMPT.format(
        me=me, frm=email.get("from_addr", ""),
        to=", ".join(email.get("to_addrs", [])), cc=", ".join(email.get("cc_addrs", [])),
        subject=email.get("subject", ""), body=(email.get("body", "") or "")[:4000],
    )
    resp = requests.post(
        f"{OLLAMA_HOST}/api/generate",
        # "json" mode (not a strict schema) — far more compatible across Ollama
        # versions/models and faster than schema-constrained decoding.
        json={"model": resolve_model(), "prompt": prompt, "stream": False,
              "format": "json", "keep_alive": OLLAMA_KEEP_ALIVE,
              "options": {"temperature": 0, "num_predict": 300}},
        timeout=OLLAMA_TIMEOUT,
    )
    resp.raise_for_status()
    data = _parse_json(resp.json().get("response", ""))
    if "board" not in data:
        raise ValueError(f"model did not return a board (got keys {list(data)})")
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
