"""Tests for output module."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from minutes.models import (
    ActionItem,
    Concept,
    Decision,
    ExtractionResult,
    Idea,
    Question,
    Term,
)
from minutes.output import (
    add_glossary_section,
    append_session_log,
    update_index,
    write_session_markdown,
)


@pytest.fixture
def sample_result():
    """Create a sample ExtractionResult for testing."""
    return ExtractionResult(
        tldr="Discussed project roadmap and Q1 planning.",
        decisions=[
            Decision(
                summary="Adopt async-first architecture",
                owner="Alice",
                rationale="Improves scalability",
                date="2024-01-15",
            ),
            Decision(
                summary="Move API to gRPC",
                owner="Bob",
                rationale="Better performance for internal services",
            ),
        ],
        ideas=[
            Idea(
                title="Rate limiting service",
                description="Dedicated service for rate limiting",
                category="opportunity",
            ),
            Idea(
                title="Cache layer",
                description="Add Redis cache",
                category="suggestion",
            ),
        ],
        questions=[
            Question(
                text="How do we handle backward compatibility?",
                context="When migrating to gRPC",
                owner="Charlie",
            ),
            Question(
                text="What's the deployment timeline?",
                context="For Q1 features",
            ),
        ],
        action_items=[
            ActionItem(
                description="Create gRPC proto definitions",
                owner="Bob",
                deadline="2024-02-15",
            ),
            ActionItem(
                description="Design caching strategy",
                owner="Alice",
            ),
        ],
        concepts=[
            Concept(
                name="Event-driven architecture",
                definition="System design using async events",
            ),
            Concept(
                name="Idempotency",
                definition="Operations can be repeated safely",
            ),
        ],
        terms=[
            Term(
                term="gRPC",
                definition="High-performance RPC framework",
                context="API communication",
            ),
            Term(
                term="TTL",
                definition="Time To Live",
                context="Cache expiration",
            ),
        ],
    )


@pytest.fixture
def sample_metadata():
    """Create sample metadata."""
    return {
        "format": "jsonl",
        "content_metric": "125 msgs",
    }


class TestWriteSessionMarkdown:
    """Test write_session_markdown function."""

    def test_write_session_markdown_creates_file(self, tmp_path, sample_result, sample_metadata):
        """Verify markdown file is created in output directory."""
        output_path = write_session_markdown(
            sample_result,
            sample_metadata,
            str(tmp_path),
            "abc123def456",
            "meeting.jsonl",
            "claude-haiku",
        )

        assert Path(output_path).exists()
        assert output_path.endswith(".md")
        assert tmp_path.name in output_path

    def test_write_session_markdown_contains_all_sections(
        self, tmp_path, sample_result, sample_metadata
    ):
        """Verify markdown contains all expected sections."""
        output_path = write_session_markdown(
            sample_result,
            sample_metadata,
            str(tmp_path),
            "abc123def456",
            "meeting.jsonl",
            "claude-haiku",
        )

        content = Path(output_path).read_text()

        # Check all section headers
        assert "# Session Notes" in content
        assert "## TLDR" in content
        assert "## Decisions" in content
        assert "## Ideas" in content
        assert "## Questions" in content
        assert "## Action Items" in content
        assert "## Concepts" in content
        assert "## Terminology" in content

    def test_write_session_markdown_contains_content(self, tmp_path, sample_result, sample_metadata):
        """Verify markdown contains actual extracted content."""
        output_path = write_session_markdown(
            sample_result,
            sample_metadata,
            str(tmp_path),
            "abc123def456",
            "meeting.jsonl",
            "claude-haiku",
        )

        content = Path(output_path).read_text()

        # Check content from various sections
        assert "Discussed project roadmap" in content
        assert "Adopt async-first architecture" in content
        assert "Alice" in content
        assert "Rate limiting service" in content
        assert "How do we handle backward compatibility?" in content
        assert "Create gRPC proto definitions" in content
        assert "Event-driven architecture" in content
        assert "gRPC" in content

    def test_write_session_markdown_skips_empty_sections(self, tmp_path, sample_metadata):
        """Verify empty sections are not included."""
        empty_result = ExtractionResult(
            tldr="No decisions made.",
            decisions=[],
            ideas=[],
            questions=[],
            action_items=[],
            concepts=[],
            terms=[],
        )

        output_path = write_session_markdown(
            empty_result,
            sample_metadata,
            str(tmp_path),
            "abc123def456",
            "meeting.jsonl",
            "claude-haiku",
        )

        content = Path(output_path).read_text()

        # TLDR should be present
        assert "## TLDR" in content
        # But empty sections should not
        assert "## Decisions" not in content
        assert "## Ideas" not in content
        assert "## Questions" not in content
        assert "## Action Items" not in content
        assert "## Concepts" not in content
        assert "## Terminology" not in content

    def test_write_session_markdown_filename_format(self, tmp_path, sample_result, sample_metadata):
        """Verify filename is in YYYY-MM-DD-HH-MM-SS.md format."""
        output_path = write_session_markdown(
            sample_result,
            sample_metadata,
            str(tmp_path),
            "abc123def456",
            "meeting.jsonl",
            "claude-haiku",
        )

        filename = Path(output_path).name
        # Should match pattern like 2024-01-15-14-30-45.md
        assert filename.endswith(".md")
        parts = filename[:-3].split("-")
        assert len(parts) == 6  # YYYY-MM-DD-HH-MM-SS
        assert parts[0].isdigit() and len(parts[0]) == 4  # Year
        assert parts[1].isdigit() and len(parts[1]) == 2  # Month
        assert parts[2].isdigit() and len(parts[2]) == 2  # Day


class TestAppendSessionLog:
    """Test append_session_log function."""

    def test_append_session_log_creates_file(self, tmp_path, sample_result, sample_metadata):
        """Verify session.log file is created."""
        append_session_log(
            str(tmp_path),
            "meeting.jsonl",
            sample_metadata,
            sample_result,
            "abc123def456",
            is_cached=False,
        )

        log_file = tmp_path / "session.log"
        assert log_file.exists()

    def test_append_session_log_format(self, tmp_path, sample_result, sample_metadata):
        """Verify log entry has correct tab-separated format."""
        append_session_log(
            str(tmp_path),
            "meeting.jsonl",
            sample_metadata,
            sample_result,
            "abc123def456",
            is_cached=False,
        )

        log_file = tmp_path / "session.log"
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) >= 1

        # Last line should be the entry we just added
        last_line = lines[-1]
        fields = last_line.split("\t")
        assert len(fields) == 9  # 9 tab-separated fields

    def test_append_session_log_fields_correct(self, tmp_path, sample_result, sample_metadata):
        """Verify log entry fields are correct."""
        append_session_log(
            str(tmp_path),
            "meeting.jsonl",
            sample_metadata,
            sample_result,
            "abc123def456",
            is_cached=False,
        )

        log_file = tmp_path / "session.log"
        lines = log_file.read_text().strip().split("\n")
        last_line = lines[-1]
        fields = last_line.split("\t")

        # Verify structure: timestamp, input_file, content_metric, decisions, ideas, questions, actions, hash, status
        assert "meeting.jsonl" in fields[1]
        assert "125 msgs" in fields[2]
        assert fields[3] == "2"  # 2 decisions
        assert fields[4] == "2"  # 2 ideas
        assert fields[5] == "2"  # 2 questions
        assert fields[6] == "2"  # 2 action items
        assert fields[7] == "abc123def456"  # First 12 chars of hash
        assert fields[8] == "new"  # Not cached

    def test_append_session_log_cached_status(self, tmp_path, sample_result, sample_metadata):
        """Verify cached status is recorded correctly."""
        append_session_log(
            str(tmp_path),
            "meeting.jsonl",
            sample_metadata,
            sample_result,
            "abc123def456",
            is_cached=True,
        )

        log_file = tmp_path / "session.log"
        lines = log_file.read_text().strip().split("\n")
        last_line = lines[-1]
        fields = last_line.split("\t")

        assert fields[8] == "cached"

    def test_append_session_log_appends_multiple_entries(
        self, tmp_path, sample_result, sample_metadata
    ):
        """Verify multiple log entries are appended correctly."""
        append_session_log(
            str(tmp_path),
            "meeting1.jsonl",
            sample_metadata,
            sample_result,
            "abc123def456",
            is_cached=False,
        )
        append_session_log(
            str(tmp_path),
            "meeting2.jsonl",
            sample_metadata,
            sample_result,
            "def456ghi789",
            is_cached=True,
        )

        log_file = tmp_path / "session.log"
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 2

        # Check both entries
        fields1 = lines[0].split("\t")
        fields2 = lines[1].split("\t")
        assert "meeting1.jsonl" in fields1[1]
        assert "meeting2.jsonl" in fields2[1]
        assert fields1[8] == "new"
        assert fields2[8] == "cached"


class TestUpdateIndex:
    """Test update_index function."""

    def test_update_index_creates_new_index(self, tmp_path, sample_result):
        """Verify index.json is created when it doesn't exist."""
        update_index(
            str(tmp_path),
            "meeting.jsonl",
            sample_result,
            "abc123def456",
            "2024-01-15-14-30-45.md",
        )

        index_file = tmp_path / "index.json"
        assert index_file.exists()

    def test_update_index_structure(self, tmp_path, sample_result):
        """Verify index.json has correct structure."""
        update_index(
            str(tmp_path),
            "meeting.jsonl",
            sample_result,
            "abc123def456",
            "2024-01-15-14-30-45.md",
        )

        index_file = tmp_path / "index.json"
        data = json.loads(index_file.read_text())

        assert data["version"] == "1.0"
        assert "generated" in data
        assert data["total_sessions"] == 1
        assert "stats" in data
        assert "sessions" in data
        assert isinstance(data["sessions"], list)

    def test_update_index_stats_calculation(self, tmp_path, sample_result):
        """Verify stats are calculated correctly."""
        update_index(
            str(tmp_path),
            "meeting.jsonl",
            sample_result,
            "abc123def456",
            "2024-01-15-14-30-45.md",
        )

        index_file = tmp_path / "index.json"
        data = json.loads(index_file.read_text())

        stats = data["stats"]
        assert stats["decisions"] == 2
        assert stats["ideas"] == 2
        assert stats["questions"] == 2
        assert stats["action_items"] == 2
        assert stats["concepts"] == 2
        assert stats["terms"] == 2

    def test_update_index_session_entry(self, tmp_path, sample_result):
        """Verify session entry is recorded correctly."""
        update_index(
            str(tmp_path),
            "meeting.jsonl",
            sample_result,
            "abc123def456",
            "2024-01-15-14-30-45.md",
            glossary_matches=1,
            glossary_unknown=2,
        )

        index_file = tmp_path / "index.json"
        data = json.loads(index_file.read_text())

        session = data["sessions"][0]
        assert session["file"] == "meeting.jsonl"
        assert session["hash"] == "abc123def456"
        assert session["output_file"] == "2024-01-15-14-30-45.md"
        assert session["counts"]["decisions"] == 2
        assert session["glossary_matches"] == 1
        assert session["glossary_unknown"] == 2

    def test_update_index_accumulates_stats(self, tmp_path, sample_result):
        """Verify stats accumulate when adding multiple sessions."""
        update_index(
            str(tmp_path),
            "meeting1.jsonl",
            sample_result,
            "abc123def456",
            "2024-01-15-14-30-45.md",
        )

        # Create a result with different counts
        result2 = ExtractionResult(
            tldr="Quick sync.",
            decisions=[Decision(summary="Test decision")],
            ideas=[],
            questions=[],
            action_items=[],
            concepts=[],
            terms=[],
        )

        update_index(
            str(tmp_path),
            "meeting2.jsonl",
            result2,
            "def456ghi789",
            "2024-01-15-15-00-00.md",
        )

        index_file = tmp_path / "index.json"
        data = json.loads(index_file.read_text())

        assert data["total_sessions"] == 2
        assert data["stats"]["decisions"] == 3  # 2 + 1
        assert data["stats"]["ideas"] == 2  # 2 + 0
        assert len(data["sessions"]) == 2

    def test_update_index_overwrites_existing(self, tmp_path, sample_result):
        """Verify index is updated atomically when it exists."""
        # Create initial index
        update_index(
            str(tmp_path),
            "meeting1.jsonl",
            sample_result,
            "abc123def456",
            "2024-01-15-14-30-45.md",
        )

        # Update with new entry
        result2 = ExtractionResult(
            tldr="Another meeting.",
            decisions=[],
            ideas=[Idea(title="Test idea")],
            questions=[],
            action_items=[],
            concepts=[],
            terms=[],
        )

        update_index(
            str(tmp_path),
            "meeting2.jsonl",
            result2,
            "def456ghi789",
            "2024-01-15-15-00-00.md",
        )

        index_file = tmp_path / "index.json"
        data = json.loads(index_file.read_text())

        # Verify both entries exist
        assert len(data["sessions"]) == 2
        files = [s["file"] for s in data["sessions"]]
        assert "meeting1.jsonl" in files
        assert "meeting2.jsonl" in files


class TestAddGlossarySection:
    """Test add_glossary_section function."""

    def test_add_glossary_section_appends_to_file(self, tmp_path, sample_result, sample_metadata):
        """Verify glossary section is appended to markdown file."""
        markdown_path = write_session_markdown(
            sample_result,
            sample_metadata,
            str(tmp_path),
            "abc123def456",
            "meeting.jsonl",
            "claude-haiku",
        )

        original_content = Path(markdown_path).read_text()

        matches = [{"term": "idempotency"}, {"term": "gRPC"}]
        unknown = [{"term": "unknown-term"}]

        add_glossary_section(markdown_path, matches, unknown)

        updated_content = Path(markdown_path).read_text()

        # Verify section was added
        assert "## Glossary Cross-Reference" in updated_content
        assert len(updated_content) > len(original_content)

    def test_add_glossary_section_shows_matches(self, tmp_path, sample_result, sample_metadata):
        """Verify matched terms are shown with checkmark."""
        markdown_path = write_session_markdown(
            sample_result,
            sample_metadata,
            str(tmp_path),
            "abc123def456",
            "meeting.jsonl",
            "claude-haiku",
        )

        matches = [{"term": "idempotency"}, {"term": "gRPC"}]
        unknown = []

        add_glossary_section(markdown_path, matches, unknown)

        content = Path(markdown_path).read_text()

        assert "✓ **idempotency**" in content
        assert "✓ **gRPC**" in content

    def test_add_glossary_section_shows_unknown(self, tmp_path, sample_result, sample_metadata):
        """Verify unknown terms are shown with question mark."""
        markdown_path = write_session_markdown(
            sample_result,
            sample_metadata,
            str(tmp_path),
            "abc123def456",
            "meeting.jsonl",
            "claude-haiku",
        )

        matches = []
        unknown = [{"term": "new-concept"}, {"term": "another-unknown"}]

        add_glossary_section(markdown_path, matches, unknown)

        content = Path(markdown_path).read_text()

        assert "? **new-concept**" in content
        assert "? **another-unknown**" in content

    def test_add_glossary_section_empty_lists(self, tmp_path, sample_result, sample_metadata):
        """Verify section is added even with empty lists."""
        markdown_path = write_session_markdown(
            sample_result,
            sample_metadata,
            str(tmp_path),
            "abc123def456",
            "meeting.jsonl",
            "claude-haiku",
        )

        add_glossary_section(markdown_path, [], [])

        content = Path(markdown_path).read_text()

        # Section should still exist even if empty
        assert "## Glossary Cross-Reference" in content
