"""Parser module for meeting minutes input files.

Handles JSONL (Claude Code interaction logs) and plain text formats.
Filters infrastructure noise: tool results, system reminders, teammate
protocol messages, compaction summaries, and other non-conversation content.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


# Message types that are never conversation content
SKIP_MESSAGE_TYPES = frozenset({
    "progress",
    "system",
    "file-history-snapshot",
    "queue-operation",
})

# Regex patterns for inline noise in text content
_SYSTEM_REMINDER_RE = re.compile(
    r"<system-reminder>.*?</system-reminder>", re.DOTALL
)
_TEAMMATE_MSG_RE = re.compile(
    r"<teammate-message[^>]*>.*?</teammate-message>", re.DOTALL
)

# Teammate protocol JSON patterns (idle notifications, shutdown, etc.)
_TEAMMATE_PROTOCOL_PATTERNS = (
    '"type":"idle_notification"',
    '"type":"shutdown_approved"',
    '"type":"shutdown_request"',
    '"type":"teammate_terminated"',
    '"type": "idle_notification"',
    '"type": "shutdown_approved"',
    '"type": "shutdown_request"',
    '"type": "teammate_terminated"',
)


def _strip_inline_noise(text: str) -> str:
    """Remove system-reminder tags, teammate messages, and protocol JSON from text."""
    text = _SYSTEM_REMINDER_RE.sub("", text)
    text = _TEAMMATE_MSG_RE.sub("", text)
    return text.strip()


def _is_protocol_message(text: str) -> bool:
    """Check if a message is purely teammate protocol JSON (idle, shutdown, etc.)."""
    stripped = text.strip()
    if not stripped:
        return True
    # Check for JSON protocol messages
    for pattern in _TEAMMATE_PROTOCOL_PATTERNS:
        if pattern in stripped:
            return True
    return False


def _is_compaction_summary(obj: dict[str, Any]) -> bool:
    """Detect compaction/context compression messages."""
    # Check for compact_boundary system subtype
    if obj.get("type") == "system" and obj.get("subtype") == "compact_boundary":
        return True

    message = obj.get("message", {})
    if not isinstance(message, dict):
        return False

    content = message.get("content")
    if isinstance(content, str):
        # Look for compaction markers in text
        if "conversation that ran out of context" in content.lower():
            return True
        if "context was compressed" in content.lower():
            return True
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "").lower()
                if "conversation that ran out of context" in text:
                    return True
                if "context was compressed" in text:
                    return True

    return False


def parse_jsonl(file_path: str) -> tuple[str, dict[str, Any]]:
    """Parse a JSONL file containing Claude Code interaction logs.

    Extracts user and assistant messages, filtering out:
    - Non-message events (progress, system, file-history-snapshot, queue-operation)
    - Tool use and tool result content blocks
    - System-reminder and teammate-message inline tags
    - Teammate protocol messages (idle notifications, shutdown requests)
    - Compaction/context compression summaries

    Args:
        file_path: Path to the JSONL file

    Returns:
        Tuple of (consolidated_text, metadata_dict) where metadata_dict contains:
        - "messages": count of extracted messages
        - "filtered": count of messages removed by filters
        - "skipped": count of unparseable lines
        - "format": "jsonl"
    """
    messages: list[str] = []
    bad_lines = 0
    filtered = 0

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

            # Skip non-message event types
            msg_type = obj.get("type", "")
            if msg_type in SKIP_MESSAGE_TYPES:
                filtered += 1
                continue

            # Skip compaction summaries
            if _is_compaction_summary(obj):
                filtered += 1
                continue

            # Must have a message dict
            if "message" not in obj:
                filtered += 1
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
                # Filter to only text blocks — skip tool_use, tool_result, and other types
                text_parts: list[str] = []
                for block in content:
                    if isinstance(block, dict):
                        block_type = block.get("type", "")
                        if block_type == "text":
                            text_parts.append(block.get("text", ""))
                        # Skip: tool_use, tool_result, image, etc.
                text = "".join(text_parts)

            # Strip inline noise (system-reminders, teammate tags)
            text = _strip_inline_noise(text)

            # Skip empty messages or pure protocol messages
            if not text or not text.strip():
                filtered += 1
                continue

            if _is_protocol_message(text):
                filtered += 1
                continue

            # Add role label
            label = "User:" if role == "user" else "Assistant:"
            messages.append(f"{label} {text}")

    consolidated_text = "\n\n".join(messages)
    metadata: dict[str, Any] = {
        "messages": len(messages),
        "filtered": filtered,
        "skipped": bad_lines,
        "format": "jsonl",
    }

    return consolidated_text, metadata


def parse_text(file_path: str) -> tuple[str, dict[str, Any]]:
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

    metadata: dict[str, Any] = {
        "format": "text",
        "chars": len(contents),
    }

    return contents, metadata


def parse_file(file_path: str) -> tuple[str, dict[str, Any]]:
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
