"""Glossary loading and keyword matching."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from minutes.models import ExtractionResult

logger = logging.getLogger(__name__)


def load_glossary(path: str) -> list[dict[str, Any]]:  # noqa: D103
    """
    Load glossary from YAML file.

    Args:
        path: Path to YAML glossary file

    Returns:
        List of glossary terms (each a dict with 'term', 'definition', etc.)
        Returns empty list if file doesn't exist or is malformed
    """
    filepath = Path(path).expanduser()

    if not filepath.exists():
        logger.warning(f"Glossary file not found: {path}")
        return []

    try:
        with open(filepath, "r") as f:
            data = yaml.safe_load(f)

        if data is None:
            return []

        # Extract terms list from glossary structure
        if isinstance(data, dict) and "terms" in data:
            terms = data.get("terms", [])
            return terms if isinstance(terms, list) else []

        # If it's just a list, return it
        if isinstance(data, list):
            return data

        return []

    except Exception as e:
        logger.warning(f"Error loading glossary from {path}: {e}")
        return []


def match_terms(
    extracted: ExtractionResult,
    glossary: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:  # noqa: D103
    """
    Match extracted terms and concepts against glossary.

    Args:
        extracted: ExtractionResult with terms and concepts
        glossary: List of glossary term dicts

    Returns:
        Tuple of (matched_terms, unknown_terms)
        Each term dict includes 'term' and 'source' keys
    """
    # Build a set of glossary terms (lowercase for case-insensitive matching)
    glossary_terms_lower = {term.get("term", "").lower(): term for term in glossary}

    matched = []
    unknown = []

    # Collect all extracted terms and concepts
    items_to_check = []

    # Add terms from the terms list
    for term in extracted.terms:
        items_to_check.append({"text": term.term, "source": "terms", "original": term.term})

    # Add terms from the concepts list (use name field)
    for concept in extracted.concepts:
        items_to_check.append(
            {"text": concept.name, "source": "concepts", "original": concept.name}
        )

    # Check each extracted item
    for item in items_to_check:
        text_lower = item["text"].lower()

        # Check for exact match (case-insensitive)
        if text_lower in glossary_terms_lower:
            # It's a match - preserve original case
            matched.append(
                {
                    "term": item["original"],
                    "source": item["source"],
                }
            )
        else:
            # Unknown term
            unknown.append(
                {
                    "term": item["original"],
                    "source": item["source"],
                }
            )

    return matched, unknown
