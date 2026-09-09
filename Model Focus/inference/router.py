"""Structured-vs-conversational output router.

Product decision (see conversation): structured JSON replies were confusing
and felt robotic — the user asked for plain, natural responses "like any
other AI model" instead of task_breakdown/overwhelm/etc. JSON payloads.
Structured mode is now disabled entirely: every message gets a plain-text
reply, regardless of what the fine-tune would otherwise pick.

Kept as a router (not just deleted) in case structured output is wanted
back later for a specific consumer (e.g. an app UI parsing JSON to render
task cards) — re-enabling would mean giving wants_structured_output real
per-message logic again instead of the constant False below.

Previous behavior (kept for history): a keyword-based safety net forced
plain text for safety-sensitive and short conversational messages, and left
everything else to the model's own trained judgment via a permissive system
prompt. That's superseded by "always plain text" now.
"""

from __future__ import annotations

PLAIN_TEXT_SUFFIX = "\n\nRéponds en texte libre normal, comme dans une conversation naturelle. N'utilise jamais de JSON, même pour découper des tâches ou lister des étapes — décris-les en phrases."


def wants_structured_output(message: str) -> bool | None:
    """Always False: structured JSON output is disabled project-wide (see
    module docstring). Kept as a function (not inlined at call sites) so
    turning it back on later is a one-line change here, not a hunt through
    inference/assistant.py and evaluation/run.py."""
    return False
