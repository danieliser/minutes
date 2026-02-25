#!/usr/bin/env python3
"""Pipe take-minutes extraction results into AutoMem via REST API.

Reads the SQLite items table produced by `minutes process` and stores
each item as an AutoMem memory. Fully decoupled — take-minutes and
AutoMem know nothing about each other; this script is the glue.

Usage:
    pipe-to-automem.py <minutes_db> <session_id> [--project <key>]

Requires: AUTOMEM_ENDPOINT and AUTOMEM_API_KEY environment variables.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
import urllib.request
import urllib.error

logger = logging.getLogger("pipe-to-automem")

IMPORTANCE_MAP = {
    "decision": 0.85,
    "action_item": 0.80,
    "concept": 0.65,
    "term": 0.60,
    "idea": 0.50,
    "question": 0.40,
}


def store_memory(endpoint: str, api_key: str, payload: dict) -> bool:
    """POST a single memory to AutoMem. Returns True on success."""
    url = f"{endpoint.rstrip('/')}/memory"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status < 400
    except (urllib.error.URLError, OSError) as e:
        logger.warning("Failed to store memory: %s", e)
        return False


def format_content(category: str, content: str, detail: str, owner: str) -> str:
    """Format an item as memory content."""
    parts = []

    if category == "decision":
        parts.append(content)
        if detail:
            parts.append(f"Rationale: {detail}")
        if owner:
            parts.append(f"Owner: {owner}")
    elif category == "action_item":
        parts.append(f"ACTION: {content}")
        if owner:
            parts.append(f"Owner: {owner}")
    elif category == "concept":
        parts.append(content)
        if detail:
            parts.append(detail)
    elif category == "term":
        parts.append(f"TERM: {content}")
        if detail:
            parts.append(detail)
    elif category == "idea":
        parts.append(content)
        if detail:
            parts.append(detail)
    elif category == "question":
        parts.append(f"QUESTION: {content}")
        if detail:
            parts.append(f"Context: {detail}")
    else:
        parts.append(content)

    return ". ".join(p for p in parts if p)


def build_tags(category: str, session_id: str, project_key: str, owner: str) -> list[str]:
    """Build tags for a memory."""
    tags = [category, f"session:{session_id}", f"project:{project_key}"]
    if owner:
        tags.append(f"owner:{owner.lower().strip()}")
    return tags


def pipe_session(db_path: str, session_id: str, project_key: str) -> dict:
    """Read items from SQLite and store in AutoMem."""
    endpoint = os.getenv("AUTOMEM_ENDPOINT", "").rstrip("/")
    api_key = os.getenv("AUTOMEM_API_KEY", "")
    if not endpoint or not api_key:
        return {"status": "skipped", "reason": "AUTOMEM_ENDPOINT or AUTOMEM_API_KEY not set"}

    if not os.path.exists(db_path):
        return {"status": "skipped", "reason": f"database not found: {db_path}"}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT category, content, detail, owner FROM items WHERE session_id = ?",
            (session_id,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return {"status": "skipped", "reason": "no items for session"}

    stored = 0
    errors = 0

    for row in rows:
        category = row["category"]
        content_text = format_content(
            category, row["content"], row["detail"] or "", row["owner"] or ""
        )
        if not content_text:
            continue

        payload = {
            "content": content_text,
            "tags": build_tags(category, session_id, project_key, row["owner"] or ""),
            "importance": IMPORTANCE_MAP.get(category, 0.5),
            "metadata": {
                "source": "take-minutes",
                "session_id": session_id,
                "category": category,
            },
        }

        if store_memory(endpoint, api_key, payload):
            stored += 1
        else:
            errors += 1

    return {"status": "complete", "stored": stored, "errors": errors, "total": len(rows)}


def main():
    parser = argparse.ArgumentParser(description="Pipe take-minutes items into AutoMem")
    parser.add_argument("db_path", help="Path to minutes.db SQLite database")
    parser.add_argument("session_id", help="Session ID to pipe")
    parser.add_argument("--project", default="unknown", help="Project key for tagging")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    result = pipe_session(args.db_path, args.session_id, args.project)
    print(json.dumps(result))

    if result["status"] == "complete":
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
