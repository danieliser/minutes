"""Tests for the AutoMem memory pipe module."""

import pytest
from unittest.mock import patch, MagicMock
from minutes.memory_pipe import (
    pipe_to_memory,
    _format_content,
    _extra_tags,
    _iter_items,
    IMPORTANCE_MAP,
)
from minutes.models import (
    ExtractionResult,
    Decision,
    ActionItem,
    Concept,
    Term,
    Idea,
    Question,
)


@pytest.fixture
def sample_result():
    return ExtractionResult(
        decisions=[
            Decision(summary="Use PostgreSQL", rationale="Better for our scale", owner="Daniel"),
        ],
        action_items=[
            ActionItem(description="Set up database", owner="Daniel", deadline="2026-03-01"),
        ],
        concepts=[
            Concept(name="Sharding", definition="Splitting data across servers"),
        ],
        terms=[
            Term(term="ORM", definition="Object-Relational Mapping", context="database layer"),
        ],
        ideas=[
            Idea(title="Add caching layer", description="Redis for hot queries", category="suggestion"),
        ],
        questions=[
            Question(text="Which region for deployment?", context="Latency requirements"),
        ],
        tldr="Database architecture decisions.",
    )


class TestFormatContent:

    def test_decision_full(self):
        item = Decision(summary="Use PostgreSQL", rationale="Better scale", owner="Daniel")
        result = _format_content("decision", item)
        assert result == "Use PostgreSQL. Rationale: Better scale. Owner: Daniel"

    def test_decision_minimal(self):
        item = Decision(summary="Use PostgreSQL")
        result = _format_content("decision", item)
        assert result == "Use PostgreSQL"

    def test_action_item_full(self):
        item = ActionItem(description="Set up DB", owner="Daniel", deadline="2026-03-01")
        result = _format_content("action_item", item)
        assert result == "ACTION: Set up DB. Owner: Daniel. Due: 2026-03-01"

    def test_concept(self):
        item = Concept(name="Sharding", definition="Splitting data")
        result = _format_content("concept", item)
        assert result == "Sharding. Splitting data"

    def test_concept_no_definition(self):
        item = Concept(name="Sharding")
        result = _format_content("concept", item)
        assert result == "Sharding"

    def test_term(self):
        item = Term(term="ORM", definition="Object-Relational Mapping", context="DB layer")
        result = _format_content("term", item)
        assert result == "TERM: ORM — Object-Relational Mapping. Context: DB layer"

    def test_idea_default_category(self):
        item = Idea(title="Add cache", description="Redis", category="suggestion")
        result = _format_content("idea", item)
        # "suggestion" is default, should be omitted
        assert result == "Add cache. Redis"
        assert "suggestion" not in result

    def test_idea_non_default_category(self):
        item = Idea(title="Fix bug", description="Critical", category="problem")
        result = _format_content("idea", item)
        assert "Category: problem" in result

    def test_question(self):
        item = Question(text="Which region?", context="Latency")
        result = _format_content("question", item)
        assert result == "QUESTION: Which region?. Context: Latency"

    def test_unknown_category(self):
        assert _format_content("unknown", object()) == ""


class TestExtraTags:

    def test_owner_tag(self):
        item = Decision(summary="x", owner="Daniel")
        tags = _extra_tags("decision", item)
        assert "owner:daniel" in tags

    def test_no_owner(self):
        item = Decision(summary="x")
        tags = _extra_tags("decision", item)
        assert not any(t.startswith("owner:") for t in tags)

    def test_deadline_tag(self):
        item = ActionItem(description="x", deadline="2026-03-01")
        tags = _extra_tags("action_item", item)
        assert "has-deadline" in tags

    def test_no_deadline_tag_for_non_action(self):
        item = Decision(summary="x", date="2026-01-01")
        tags = _extra_tags("decision", item)
        assert "has-deadline" not in tags


class TestIterItems:

    def test_yields_non_empty_only(self, sample_result):
        categories = [cat for cat, _ in _iter_items(sample_result)]
        assert "decision" in categories
        assert "action_item" in categories
        assert "concept" in categories
        assert "term" in categories
        assert "idea" in categories
        assert "question" in categories

    def test_skips_empty(self):
        result = ExtractionResult(decisions=[Decision(summary="x")])
        categories = [cat for cat, _ in _iter_items(result)]
        assert categories == ["decision"]

    def test_empty_result(self):
        result = ExtractionResult()
        assert list(_iter_items(result)) == []


class TestImportanceMap:

    def test_tiers(self):
        assert IMPORTANCE_MAP["decision"] > IMPORTANCE_MAP["action_item"]
        assert IMPORTANCE_MAP["action_item"] > IMPORTANCE_MAP["concept"]
        assert IMPORTANCE_MAP["concept"] > IMPORTANCE_MAP["term"]
        assert IMPORTANCE_MAP["term"] > IMPORTANCE_MAP["idea"]
        assert IMPORTANCE_MAP["idea"] > IMPORTANCE_MAP["question"]


class TestPipeToMemory:

    @patch.dict("os.environ", {}, clear=True)
    def test_skips_when_not_configured(self, sample_result):
        result = pipe_to_memory(sample_result, "sess-123", "project-x")
        assert result["status"] == "skipped"

    @patch.dict("os.environ", {"AUTOMEM_ENDPOINT": "http://localhost:8001", "AUTOMEM_API_KEY": "test-key"})
    @patch("minutes.memory_pipe.requests")
    def test_stores_all_items(self, mock_requests, sample_result):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_requests.post.return_value = mock_response

        result = pipe_to_memory(sample_result, "sess-123", "project-x")

        assert result["status"] == "complete"
        assert result["stored"] == 6  # 1 of each category
        assert result["errors"] == 0
        assert mock_requests.post.call_count == 6

        # Check first call has correct structure
        call_args = mock_requests.post.call_args_list[0]
        assert call_args[0][0] == "http://localhost:8001/memory"
        payload = call_args[1]["json"]
        assert "decision" in payload["tags"]
        assert "session:sess-123" in payload["tags"]
        assert "project:project-x" in payload["tags"]
        assert payload["importance"] == 0.85
        assert payload["metadata"]["source"] == "take-minutes"

    @patch.dict("os.environ", {"AUTOMEM_ENDPOINT": "http://localhost:8001", "AUTOMEM_API_KEY": "test-key"})
    @patch("minutes.memory_pipe.requests")
    def test_handles_api_errors(self, mock_requests, sample_result):
        mock_requests.post.side_effect = Exception("Connection refused")

        result = pipe_to_memory(sample_result, "sess-123", "project-x")

        assert result["status"] == "complete"
        assert result["stored"] == 0
        assert result["errors"] == 6

    @patch.dict("os.environ", {"AUTOMEM_ENDPOINT": "http://localhost:8001/", "AUTOMEM_API_KEY": "test-key"})
    @patch("minutes.memory_pipe.requests")
    def test_strips_trailing_slash(self, mock_requests, sample_result):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_requests.post.return_value = mock_response

        pipe_to_memory(sample_result, "sess-123", "project-x")

        call_url = mock_requests.post.call_args_list[0][0][0]
        assert call_url == "http://localhost:8001/memory"

    @patch.dict("os.environ", {"AUTOMEM_ENDPOINT": "http://localhost:8001", "AUTOMEM_API_KEY": "test-key"})
    @patch("minutes.memory_pipe.requests")
    def test_empty_result_stores_nothing(self, mock_requests):
        result = pipe_to_memory(ExtractionResult(), "sess-123", "project-x")

        assert result["status"] == "complete"
        assert result["stored"] == 0
        assert result["errors"] == 0
        mock_requests.post.assert_not_called()
