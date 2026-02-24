"""Markdown, log, and index writing for session outputs."""

import json
import logging
from datetime import datetime
from pathlib import Path

from minutes.models import ExtractionResult

logger = logging.getLogger(__name__)


def write_session_markdown(
    result: ExtractionResult,
    metadata: dict,
    output_dir: str,
    file_hash: str,
    input_file: str,
    backend_name: str,
) -> str:
    """
    Generate and write a markdown file with extracted session content.

    Args:
        result: ExtractionResult containing all extracted data
        metadata: Metadata dict with 'content_metric' and 'format' keys
        output_dir: Directory to write markdown file to
        file_hash: Hash of input file
        input_file: Name of input file
        backend_name: Name of backend used (e.g., "claude-haiku")

    Returns:
        Path to the generated markdown file
    """
    # Create output directory if it doesn't exist
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Generate timestamp and filename
    now = datetime.now()
    timestamp_str = now.strftime("%Y-%m-%d-%H-%M-%S")
    filename = f"{timestamp_str}.md"
    filepath = output_path / filename

    # Build markdown content
    lines = []

    # Header
    readable_timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    lines.append(f"# Session Notes — {readable_timestamp}")
    lines.append("")

    # Metadata line
    chunk_count = metadata.get("format", "text")
    if "msgs" in metadata.get("content_metric", ""):
        chunk_info = metadata.get("content_metric", "")
    else:
        chunk_info = metadata.get("content_metric", "0 msgs")

    hash_short = file_hash[:12] if file_hash else "unknown"
    lines.append(f"**Input:** `{input_file}` ({backend_name}, {chunk_info})")
    lines.append(f"**Hash:** `{hash_short}...` (new)")
    lines.append("")

    # TLDR section (always include if present)
    if result.tldr:
        lines.append("## TLDR")
        lines.append(result.tldr)
        lines.append("")

    # Decisions section
    if result.decisions:
        lines.append("## Decisions")
        for i, decision in enumerate(result.decisions, 1):
            reason_text = f"reason: {decision.rationale}" if decision.rationale else ""
            owner_text = f", owner: {decision.owner}" if decision.owner else ""
            extra = f"({reason_text}{owner_text})"
            lines.append(f"{i}. {decision.summary} {extra}".rstrip())
        lines.append("")

    # Ideas section
    if result.ideas:
        lines.append("## Ideas")
        for i, idea in enumerate(result.ideas, 1):
            lines.append(f"{i}. **{idea.title}** — {idea.category}: {idea.description}")
        lines.append("")

    # Questions section
    if result.questions:
        lines.append("## Questions")
        for i, question in enumerate(result.questions, 1):
            context_text = f"(context: {question.context})" if question.context else ""
            lines.append(f"{i}. {question.text} {context_text}".rstrip())
        lines.append("")

    # Action Items section
    if result.action_items:
        lines.append("## Action Items")
        for action in result.action_items:
            owner_text = f"Owner: {action.owner}" if action.owner else "Owner: Unassigned"
            due_text = f", Due: {action.deadline}" if action.deadline else ""
            lines.append(f"- [ ] {action.description} — {owner_text}{due_text}")
        lines.append("")

    # Concepts section
    if result.concepts:
        lines.append("## Concepts")
        for concept in result.concepts:
            lines.append(f"- **{concept.name}:** {concept.definition}")
        lines.append("")

    # Terminology section
    if result.terms:
        lines.append("## Terminology")
        for term in result.terms:
            context_text = f" ({term.context})" if term.context else ""
            lines.append(f"- **{term.term}:** {term.definition}{context_text}")
        lines.append("")

    # Write to file
    content = "\n".join(lines).rstrip() + "\n"
    filepath.write_text(content)

    return str(filepath)


def append_session_log(
    output_dir: str,
    input_file: str,
    metadata: dict,
    result: ExtractionResult,
    file_hash: str,
    is_cached: bool,
) -> None:
    """
    Append a session entry to the session.log file.

    Args:
        output_dir: Directory containing session.log
        input_file: Name of input file
        metadata: Metadata dict with content_metric
        result: ExtractionResult with extracted counts
        file_hash: Hash of input file
        is_cached: Whether this result was cached
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    log_file = output_path / "session.log"

    # Get current ISO timestamp
    timestamp = datetime.now().isoformat()

    # Get content metric from metadata
    content_metric = metadata.get("content_metric", "0 msgs")

    # Count extracted items
    decisions_count = len(result.decisions)
    ideas_count = len(result.ideas)
    questions_count = len(result.questions)
    actions_count = len(result.action_items)

    # Hash first 12 characters
    hash_12 = file_hash[:12] if file_hash else "unknown"

    # Status
    status = "cached" if is_cached else "new"

    # Build tab-separated line
    fields = [
        timestamp,
        input_file,
        content_metric,
        str(decisions_count),
        str(ideas_count),
        str(questions_count),
        str(actions_count),
        hash_12,
        status,
    ]

    line = "\t".join(fields)

    # Append to log file
    with open(log_file, "a") as f:
        f.write(line + "\n")


def update_index(
    output_dir: str,
    input_file: str,
    result: ExtractionResult,
    file_hash: str,
    output_file: str,
    glossary_matches: int = 0,
    glossary_unknown: int = 0,
) -> None:
    """
    Update or create the index.json file with session metadata and stats.

    Args:
        output_dir: Directory containing index.json
        input_file: Name of input file
        result: ExtractionResult with extracted data
        file_hash: Hash of input file
        output_file: Name of output markdown file
        glossary_matches: Number of glossary matches
        glossary_unknown: Number of unknown glossary terms
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    index_file = output_path / "index.json"

    # Load existing index or create new
    if index_file.exists():
        data = json.loads(index_file.read_text())
    else:
        data = {
            "version": "1.0",
            "generated": datetime.now().isoformat(),
            "total_sessions": 0,
            "stats": {
                "decisions": 0,
                "ideas": 0,
                "questions": 0,
                "action_items": 0,
                "concepts": 0,
                "terms": 0,
            },
            "sessions": [],
        }

    # Update aggregate stats
    counts = {
        "decisions": len(result.decisions),
        "ideas": len(result.ideas),
        "questions": len(result.questions),
        "action_items": len(result.action_items),
        "concepts": len(result.concepts),
        "terms": len(result.terms),
    }

    for key in counts:
        data["stats"][key] += counts[key]

    # Add session entry
    session_entry = {
        "date": datetime.now().isoformat(),
        "file": input_file,
        "hash": file_hash[:12],
        "output_file": output_file,
        "counts": counts,
        "glossary_matches": glossary_matches,
        "glossary_unknown": glossary_unknown,
    }

    data["sessions"].append(session_entry)
    data["total_sessions"] = len(data["sessions"])
    data["generated"] = datetime.now().isoformat()

    # Write atomically (write to temp file, then rename)
    temp_file = index_file.with_suffix(".json.tmp")
    temp_file.write_text(json.dumps(data, indent=2))
    temp_file.replace(index_file)


def add_glossary_section(
    markdown_path: str,
    matches: list[dict],
    unknown: list[dict],
) -> None:
    """
    Append a Glossary Cross-Reference section to an existing markdown file.

    Args:
        markdown_path: Path to markdown file
        matches: List of matched glossary terms (dicts with 'term' key)
        unknown: List of unknown terms (dicts with 'term' key)
    """
    filepath = Path(markdown_path)

    # Build glossary section
    lines = []
    lines.append("## Glossary Cross-Reference")
    lines.append("")

    # Add matched terms
    for item in matches:
        term = item.get("term", "")
        lines.append(f"- ✓ **{term}** — matches known concept")

    # Add unknown terms
    for item in unknown:
        term = item.get("term", "")
        lines.append(f"- ? **{term}** — unknown term (not in glossary)")

    section = "\n".join(lines)

    # Append to file
    current_content = filepath.read_text()
    if not current_content.endswith("\n"):
        current_content += "\n"

    new_content = current_content + "\n" + section + "\n"
    filepath.write_text(new_content)
