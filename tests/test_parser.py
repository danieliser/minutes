"""Tests for the parser module."""

import json
import pytest
from pathlib import Path
from minutes.parser import parse_jsonl, parse_text, parse_file


@pytest.fixture
def fixtures_dir():
    """Return path to test fixtures directory."""
    return Path(__file__).parent / "fixtures"


class TestParseJsonl:
    """Tests for parse_jsonl function."""

    def test_parse_jsonl_extracts_user_and_assistant_messages(self, fixtures_dir):
        """Verify JSONL parser extracts user and assistant messages."""
        text, metadata = parse_jsonl(str(fixtures_dir / "sample.jsonl"))

        # Should have 4 messages: 2 user, 2 assistant
        assert metadata["messages"] == 4
        assert metadata["skipped"] == 0
        assert metadata["format"] == "jsonl"

        # Verify messages are labeled and in order
        assert "User: What architecture should we use?" in text
        assert "Assistant: I recommend a layered architecture." in text
        assert "User: Let's go with microservices." in text
        assert "Assistant: Good choice. I'll set up the project structure." in text

    def test_parse_jsonl_filters_tool_use_blocks(self, fixtures_dir):
        """Verify tool_use blocks are filtered from assistant messages."""
        text, metadata = parse_jsonl(str(fixtures_dir / "sample.jsonl"))

        # tool_use block should not appear in output
        assert "tool_use" not in text
        assert "Read" not in text
        assert "/some/file" not in text

    def test_parse_jsonl_skips_non_message_events(self, fixtures_dir):
        """Verify non-message events are skipped."""
        text, metadata = parse_jsonl(str(fixtures_dir / "sample.jsonl"))

        # file-history-snapshot and progress events should be skipped
        assert "file-history-snapshot" not in text
        assert "hook_progress" not in text

    def test_parse_jsonl_skips_tool_role_messages(self, fixtures_dir):
        """Verify tool role messages are skipped."""
        text, metadata = parse_jsonl(str(fixtures_dir / "sample.jsonl"))

        # tool_result message with role="tool" should be skipped
        assert "file contents here" not in text

    def test_parse_jsonl_with_malformed_lines(self, tmp_path):
        """Verify malformed JSON lines are skipped and counted."""
        jsonl_file = tmp_path / "malformed.jsonl"
        jsonl_file.write_text(
            '{"type": "user", "message": {"role": "user", "content": "Valid message"}}\n'
            'not valid json at all\n'
            '{"type": "user", "message": {"role": "user", "content": "Another valid"}}\n'
        )

        text, metadata = parse_jsonl(str(jsonl_file))

        assert metadata["messages"] == 2
        assert metadata["skipped"] == 1
        assert "Valid message" in text
        assert "Another valid" in text

    def test_parse_jsonl_skips_empty_messages(self, tmp_path):
        """Verify empty messages are skipped."""
        jsonl_file = tmp_path / "empty_messages.jsonl"
        jsonl_file.write_text(
            '{"type": "user", "message": {"role": "user", "content": ""}}\n'
            '{"type": "user", "message": {"role": "user", "content": "   "}}\n'
            '{"type": "user", "message": {"role": "user", "content": []}}\n'
            '{"type": "user", "message": {"role": "user", "content": "Real message"}}\n'
        )

        text, metadata = parse_jsonl(str(jsonl_file))

        assert metadata["messages"] == 1
        assert "Real message" in text

    def test_parse_jsonl_handles_content_as_list(self, tmp_path):
        """Verify content as list of blocks is handled correctly."""
        jsonl_file = tmp_path / "content_list.jsonl"
        jsonl_file.write_text(
            '{"type": "assistant", "message": {"role": "assistant", "content": '
            '[{"type": "text", "text": "First "}, {"type": "text", "text": "Second"}]}}\n'
        )

        text, metadata = parse_jsonl(str(jsonl_file))

        assert metadata["messages"] == 1
        assert "Assistant: First Second" in text

    def test_parse_jsonl_handles_content_as_string(self, tmp_path):
        """Verify content as string is handled correctly."""
        jsonl_file = tmp_path / "content_string.jsonl"
        jsonl_file.write_text(
            '{"type": "user", "message": {"role": "user", "content": "Plain string content"}}\n'
        )

        text, metadata = parse_jsonl(str(jsonl_file))

        assert metadata["messages"] == 1
        assert "User: Plain string content" in text

    def test_parse_jsonl_skips_unknown_roles(self, tmp_path):
        """Verify unknown roles are skipped."""
        jsonl_file = tmp_path / "unknown_role.jsonl"
        jsonl_file.write_text(
            '{"type": "system", "message": {"role": "system", "content": "system prompt"}}\n'
            '{"type": "user", "message": {"role": "user", "content": "valid"}}\n'
        )

        text, metadata = parse_jsonl(str(jsonl_file))

        assert metadata["messages"] == 1
        assert "system prompt" not in text
        assert "valid" in text


class TestParseText:
    """Tests for parse_text function."""

    def test_parse_text_returns_full_content(self, fixtures_dir):
        """Verify text parser returns full file content."""
        text, metadata = parse_text(str(fixtures_dir / "sample.txt"))

        assert "Meeting Notes - Project Kickoff" in text
        assert "Decision: Use Python for the backend" in text
        assert "Action: Daniel to set up CI/CD by Friday" in text
        assert metadata["format"] == "text"
        assert metadata["chars"] == len(text)

    def test_parse_text_empty_file(self, tmp_path):
        """Verify empty file is handled correctly."""
        empty_file = tmp_path / "empty.txt"
        empty_file.write_text("")

        text, metadata = parse_text(str(empty_file))

        assert text == ""
        assert metadata["format"] == "text"
        assert metadata["chars"] == 0

    def test_parse_text_preserves_formatting(self, tmp_path):
        """Verify text formatting is preserved."""
        text_file = tmp_path / "formatted.txt"
        content = "Line 1\n\nLine 2\n  Indented line\n"
        text_file.write_text(content)

        text, metadata = parse_text(str(text_file))

        assert text == content
        assert metadata["chars"] == len(content)


class TestParseFile:
    """Tests for parse_file auto-detection."""

    def test_parse_file_detects_jsonl(self, fixtures_dir):
        """Verify .jsonl extension triggers JSONL parser."""
        text, metadata = parse_file(str(fixtures_dir / "sample.jsonl"))

        assert metadata["format"] == "jsonl"
        assert metadata["messages"] == 4

    def test_parse_file_detects_txt(self, fixtures_dir):
        """Verify .txt extension triggers text parser."""
        text, metadata = parse_file(str(fixtures_dir / "sample.txt"))

        assert metadata["format"] == "text"
        assert "Meeting Notes" in text

    def test_parse_file_detects_md(self, tmp_path):
        """Verify .md extension triggers text parser."""
        md_file = tmp_path / "notes.md"
        md_file.write_text("# Header\n\nContent")

        text, metadata = parse_file(str(md_file))

        assert metadata["format"] == "text"
        assert "# Header" in text

    def test_parse_file_detects_markdown(self, tmp_path):
        """Verify .markdown extension triggers text parser."""
        md_file = tmp_path / "notes.markdown"
        md_file.write_text("# Header\n\nContent")

        text, metadata = parse_file(str(md_file))

        assert metadata["format"] == "text"
        assert "# Header" in text

    def test_parse_file_unknown_extension_tries_jsonl(self, tmp_path):
        """Verify unknown extension tries JSONL first."""
        jsonl_file = tmp_path / "data.unknown"
        jsonl_file.write_text(
            '{"type": "user", "message": {"role": "user", "content": "test"}}\n'
        )

        text, metadata = parse_file(str(jsonl_file))

        assert metadata["format"] == "jsonl"
        assert "test" in text

    def test_parse_file_unknown_extension_falls_back_to_text(self, tmp_path):
        """Verify unknown extension falls back to text if JSONL fails."""
        text_file = tmp_path / "data.unknown"
        text_file.write_text("Plain text content")

        text, metadata = parse_file(str(text_file))

        assert metadata["format"] == "text"
        assert "Plain text content" in text

    def test_parse_file_nonexistent_raises_error(self, tmp_path):
        """Verify FileNotFoundError is raised for missing files."""
        nonexistent = tmp_path / "doesnotexist.jsonl"

        with pytest.raises(FileNotFoundError):
            parse_file(str(nonexistent))


class TestIntegration:
    """Integration tests."""

    def test_full_workflow_jsonl(self, fixtures_dir):
        """Verify full workflow with JSONL fixture."""
        text, metadata = parse_file(str(fixtures_dir / "sample.jsonl"))

        # Check metadata
        assert metadata["format"] == "jsonl"
        assert metadata["messages"] == 4
        assert metadata["skipped"] == 0

        # Check content
        lines = text.split("\n\n")
        assert len(lines) == 4
        assert all(line.startswith(("User:", "Assistant:")) for line in lines)

    def test_full_workflow_text(self, fixtures_dir):
        """Verify full workflow with text fixture."""
        text, metadata = parse_file(str(fixtures_dir / "sample.txt"))

        # Check metadata
        assert metadata["format"] == "text"
        assert metadata["chars"] > 0

        # Check content is preserved
        assert "Meeting Notes" in text
        assert "Decision:" in text
        assert "Action:" in text
