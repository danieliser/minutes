"""Parser module for meeting minutes input files.

Handles JSONL (Claude Code interaction logs) and plain text formats.
"""

import json
from pathlib import Path
from typing import Any


def parse_jsonl(file_path: str) -> tuple[str, dict]:
    """Parse a JSONL file containing Claude Code interaction logs.

    Extracts user and assistant messages, filtering out tool_use blocks
    and non-message events (progress, file-history-snapshot, etc.).

    Args:
        file_path: Path to the JSONL file

    Returns:
        Tuple of (consolidated_text, metadata_dict) where metadata_dict contains:
        - "messages": count of extracted messages
        - "skipped": count of unparseable lines
        - "format": "jsonl"
    """
    messages = []
    bad_lines = 0

    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                bad_lines += 1
                continue

            # Skip non-message events (progress, file-history-snapshot, tool_result, etc.)
            if "message" not in obj:
                continue

            message = obj["message"]
            if not isinstance(message, dict):
                continue

            role = message.get("role")
            if role not in ("user", "assistant"):
                continue

            # Extract content - can be string or list of content blocks
            content = message.get("content")
            if content is None:
                continue

            text = ""
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                # Filter to only text blocks, skip tool_use and other types
                text_parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                text = "".join(text_parts)

            # Skip empty messages
            if not text or not text.strip():
                continue

            # Add role label
            label = "User:" if role == "user" else "Assistant:"
            messages.append(f"{label} {text}")

    consolidated_text = "\n\n".join(messages)
    metadata = {
        "messages": len(messages),
        "skipped": bad_lines,
        "format": "jsonl"
    }

    return consolidated_text, metadata


def parse_text(file_path: str) -> tuple[str, dict]:
    """Parse a plain text file.

    Args:
        file_path: Path to the text file

    Returns:
        Tuple of (file_contents, metadata_dict) where metadata_dict contains:
        - "format": "text"
        - "chars": character count
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        contents = f.read()

    metadata = {
        "format": "text",
        "chars": len(contents)
    }

    return contents, metadata


def parse_file(file_path: str) -> tuple[str, dict]:
    """Auto-detect file format and parse accordingly.

    Supports:
    - .jsonl files (Claude Code interaction logs)
    - .txt, .md, .markdown files (plain text)
    - Unknown extensions: tries JSONL first, falls back to text

    Args:
        file_path: Path to the file

    Returns:
        Tuple of (content, metadata_dict)

    Raises:
        FileNotFoundError: If file doesn't exist
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Check extension
    suffix = path.suffix.lower()

    if suffix == ".jsonl":
        return parse_jsonl(file_path)
    elif suffix in (".txt", ".md", ".markdown"):
        return parse_text(file_path)
    else:
        # Unknown extension: try JSONL first, fall back to text
        try:
            text, metadata = parse_jsonl(file_path)
            # If we successfully parsed at least one message, treat as JSONL
            if metadata.get("messages", 0) > 0:
                return text, metadata
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
        # Fall back to text parsing
        return parse_text(file_path)
