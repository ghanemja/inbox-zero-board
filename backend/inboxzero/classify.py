"""Orchestrator — rules → Gemma → confidence gate.

The reliability backbone: deterministic rules decide what they can; Gemma handles
the rest; anything below threshold is routed to `needs_review` and never auto-acted.
Every result carries its reasoning + deciding layer for audit. See learning-logic.md §4.
"""
from __future__ import annotations

from datetime import datetime, timezone

from config import CONFIDENCE_THRESHOLD
from . import rules


def classify_email(email: dict, me: str, use_gemma: bool = True) -> dict:
    result = rules.classify(email, me)

    if result is None:
        if use_gemma:
            try:
                from . import gemma  # lazy — only needs `requests` when actually used
                result = gemma.classify(email, me)
            except Exception as exc:  # Ollama down / model missing → fail safe to review
                result = _review(f"gemma unavailable ({exc})")
        else:
            result = _review("ambiguous, no gemma")

    # confidence gate — never auto-act on low confidence
    if result.get("confidence", 0) < CONFIDENCE_THRESHOLD and result["board"] != "awareness":
        result["board"] = "needs_review"
        result["reasoning"] = f"low confidence ({result.get('confidence', 0):.2f}) — {result['reasoning']}"

    result["email_id"] = email["id"]
    result["decided_at"] = datetime.now(timezone.utc).isoformat()
    result.setdefault("task", None)
    result.setdefault("due", None)
    result.setdefault("project_key", None)
    result.setdefault("topics", [])
    return result


def _review(reason: str) -> dict:
    return {"board": "needs_review", "confidence": 0.0, "reasoning": reason, "layer": "rules",
            "task": None, "due": None, "project_key": None, "topics": []}
