"""Pipe extraction results into AutoMem via REST API."""

from __future__ import annotations

import logging
import os

import requests

from minutes.models import ExtractionResult

logger = logging.getLogger(__name__)

IMPORTANCE_MAP = {
    "decision": 0.85,
    "action_item": 0.80,
    "concept": 0.65,
    "term": 0.60,
    "idea": 0.50,
    "question": 0.40,
}


def pipe_to_memory(
    result: ExtractionResult, session_id: str, project_key: str
) -> dict:
    """Store extraction results in AutoMem via REST API.

    Reads AUTOMEM_ENDPOINT and AUTOMEM_API_KEY from environment.
    Returns silently if not configured.
    """
    endpoint = os.getenv("AUTOMEM_ENDPOINT", "").rstrip("/")
    api_key = os.getenv("AUTOMEM_API_KEY", "")
    if not endpoint or not api_key:
        logger.debug("AutoMem not configured, skipping memory pipe")
        return {"status": "skipped", "reason": "not configured"}

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    url = f"{endpoint}/memory"
    stored = 0
    errors = 0

    for category, items in _iter_items(result):
        importance = IMPORTANCE_MAP.get(category, 0.5)
        base_tags = [category, f"session:{session_id}", f"project:{project_key}"]

        for item in items:
            content = _format_content(category, item)
            if not content:
                continue

            payload = {
                "content": content,
                "tags": base_tags + _extra_tags(category, item),
                "importance": importance,
                "metadata": {
                    "source": "take-minutes",
                    "session_id": session_id,
                    "category": category,
                },
            }

            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=10)
                resp.raise_for_status()
                stored += 1
            except Exception as e:
                logger.warning("Failed to store %s memory: %s", category, e)
                errors += 1

    return {"status": "complete", "stored": stored, "errors": errors}


def _iter_items(result: ExtractionResult):
    """Yield (category_name, items_list) for non-empty categories."""
    mapping = [
        ("decision", result.decisions),
        ("action_item", result.action_items),
        ("concept", result.concepts),
        ("term", result.terms),
        ("idea", result.ideas),
        ("question", result.questions),
    ]
    for category, items in mapping:
        if items:
            yield category, items


def _format_content(category: str, item) -> str:
    """Format an extraction item as memory content."""
    if category == "decision":
        parts = [item.summary]
        if item.rationale:
            parts.append(f"Rationale: {item.rationale}")
        if item.owner:
            parts.append(f"Owner: {item.owner}")
        return ". ".join(parts)

    if category == "action_item":
        parts = [f"ACTION: {item.description}"]
        if item.owner:
            parts.append(f"Owner: {item.owner}")
        if item.deadline:
            parts.append(f"Due: {item.deadline}")
        return ". ".join(parts)

    if category == "concept":
        if item.definition:
            return f"{item.name}. {item.definition}"
        return item.name

    if category == "term":
        parts = [f"TERM: {item.term} — {item.definition}"]
        if item.context:
            parts.append(f"Context: {item.context}")
        return ". ".join(parts)

    if category == "idea":
        parts = [item.title]
        if item.description:
            parts.append(item.description)
        if item.category and item.category != "suggestion":
            parts.append(f"Category: {item.category}")
        return ". ".join(parts)

    if category == "question":
        parts = [f"QUESTION: {item.text}"]
        if item.context:
            parts.append(f"Context: {item.context}")
        return ". ".join(parts)

    return ""


def _extra_tags(category: str, item) -> list[str]:
    """Build additional tags from item attributes."""
    tags = []
    owner = getattr(item, "owner", "")
    if owner:
        tags.append(f"owner:{owner.lower().strip()}")
    if category == "action_item" and getattr(item, "deadline", ""):
        tags.append("has-deadline")
    return tags
