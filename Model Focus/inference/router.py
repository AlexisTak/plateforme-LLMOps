"""Output-format instructions shared by chat and evaluation."""

from __future__ import annotations

PLAIN_TEXT_SUFFIX = "\n\nRéponds en texte libre normal, comme dans une conversation naturelle. N'utilise jamais de JSON, même pour découper des tâches ou lister des étapes — décris-les en phrases."
JSON_SUFFIX = "\n\nRéponds uniquement avec un objet JSON valide, sans bloc Markdown ni texte avant ou après. Respecte le schéma décrit dans ta mission ou dans la demande."


def output_suffix(mode: str) -> str:
    if mode == "natural":
        return PLAIN_TEXT_SUFFIX
    if mode == "json":
        return JSON_SUFFIX
    return ""
