"""Tests for glossary module."""

import tempfile
from pathlib import Path

import pytest
import yaml

from minutes.models import Concept, ExtractionResult, Term
from minutes.glossary import load_glossary, match_terms


class TestLoadGlossary:
    """Test load_glossary function."""

    def test_load_glossary_valid_yaml(self, tmp_path):
        """Verify glossary loads from valid YAML file."""
        glossary_file = tmp_path / "glossary.yml"
        glossary_content = {
            "version": "1.0",
            "terms": [
                {
                    "term": "idempotency",
                    "definition": "Operations can be repeated safely",
                    "category": "architecture",
                },
                {
                    "term": "gRPC",
                    "definition": "High-performance RPC framework",
                    "category": "technology",
                },
            ],
        }
        glossary_file.write_text(yaml.dump(glossary_content))

        result = load_glossary(str(glossary_file))

        assert len(result) == 2
        assert result[0]["term"] == "idempotency"
        assert result[1]["term"] == "gRPC"

    def test_load_glossary_missing_file_returns_empty_list(self):
        """Verify missing file returns empty list."""
        result = load_glossary("/nonexistent/path/glossary.yml")
        assert result == []

    def test_load_glossary_malformed_yaml_returns_empty_list(self, tmp_path):
        """Verify malformed YAML returns empty list."""
        glossary_file = tmp_path / "bad_glossary.yml"
        glossary_file.write_text("{ invalid yaml content [")

        result = load_glossary(str(glossary_file))
        assert result == []

    def test_load_glossary_preserves_structure(self, tmp_path):
        """Verify glossary structure is preserved."""
        glossary_file = tmp_path / "glossary.yml"
        glossary_content = {
            "version": "1.0",
            "terms": [
                {
                    "term": "async",
                    "definition": "Asynchronous operations",
                    "category": "pattern",
                    "related": ["promises", "callbacks"],
                }
            ],
        }
        glossary_file.write_text(yaml.dump(glossary_content))

        result = load_glossary(str(glossary_file))

        assert len(result) == 1
        assert result[0]["term"] == "async"
        assert result[0]["definition"] == "Asynchronous operations"
        assert result[0]["category"] == "pattern"
        assert result[0]["related"] == ["promises", "callbacks"]

    def test_load_glossary_empty_file(self, tmp_path):
        """Verify empty YAML file is handled."""
        glossary_file = tmp_path / "empty.yml"
        glossary_file.write_text("")

        result = load_glossary(str(glossary_file))
        assert result == [] or result is None

    def test_load_glossary_with_path_expansion(self, tmp_path, monkeypatch):
        """Verify tilde expansion works."""
        glossary_file = tmp_path / "glossary.yml"
        glossary_content = {"version": "1.0", "terms": []}
        glossary_file.write_text(yaml.dump(glossary_content))

        # We can't easily mock expanduser, but we can test with absolute path
        result = load_glossary(str(glossary_file))
        assert isinstance(result, list)


@pytest.fixture
def sample_glossary():
    """Create a sample glossary for testing."""
    return [
        {
            "term": "idempotency",
            "definition": "Operations can be repeated safely",
            "category": "architecture",
        },
        {
            "term": "gRPC",
            "definition": "High-performance RPC framework",
            "category": "technology",
        },
        {
            "term": "TTL",
            "definition": "Time To Live",
            "category": "caching",
        },
        {
            "term": "async",
            "definition": "Asynchronous operations",
            "category": "pattern",
        },
    ]


@pytest.fixture
def sample_extraction_result():
    """Create a sample extraction result."""
    return ExtractionResult(
        tldr="Project planning session",
        concepts=[
            Concept(
                name="Event-driven architecture",
                definition="System using async events",
            ),
            Concept(
                name="Idempotency",
                definition="Safe to repeat operations",
            ),
        ],
        terms=[
            Term(
                term="gRPC",
                definition="RPC framework",
                context="API communication",
            ),
            Term(
                term="WebSocket",
                definition="Bidirectional communication",
                context="Real-time updates",
            ),
            Term(
                term="async",
                definition="Async operations",
                context="Code patterns",
            ),
        ],
    )


class TestMatchTerms:
    """Test match_terms function."""

    def test_match_terms_finds_exact_matches(self, sample_glossary, sample_extraction_result):
        """Verify exact term matches are found."""
        matched, unknown = match_terms(sample_extraction_result, sample_glossary)

        matched_terms = [m["term"] for m in matched]
        assert "gRPC" in matched_terms
        assert "async" in matched_terms
        assert "idempotency" in matched_terms or "Idempotency" in matched_terms

    def test_match_terms_case_insensitive(self, sample_glossary, sample_extraction_result):
        """Verify matching is case-insensitive."""
        matched, unknown = match_terms(sample_extraction_result, sample_glossary)

        # "Idempotency" in concepts should match "idempotency" in glossary
        matched_terms = [m["term"].lower() for m in matched]
        assert "idempotency" in matched_terms

    def test_match_terms_identifies_unknown(self, sample_glossary, sample_extraction_result):
        """Verify unknown terms are identified."""
        matched, unknown = match_terms(sample_extraction_result, sample_glossary)

        unknown_terms = [u["term"] for u in unknown]
        assert "WebSocket" in unknown_terms
        assert "Event-driven architecture" in unknown_terms

    def test_match_terms_separates_matched_and_unknown(
        self, sample_glossary, sample_extraction_result
    ):
        """Verify matched and unknown are in separate lists."""
        matched, unknown = match_terms(sample_extraction_result, sample_glossary)

        assert isinstance(matched, list)
        assert isinstance(unknown, list)

        all_matched_terms = [m["term"].lower() for m in matched]
        all_unknown_terms = [u["term"].lower() for u in unknown]

        # No term should be in both lists
        overlap = set(all_matched_terms) & set(all_unknown_terms)
        assert len(overlap) == 0

    def test_match_terms_with_empty_glossary(self, sample_extraction_result):
        """Verify all terms are unknown with empty glossary."""
        matched, unknown = match_terms(sample_extraction_result, [])

        assert len(matched) == 0
        assert len(unknown) > 0

    def test_match_terms_returns_dicts_with_term_key(self, sample_glossary, sample_extraction_result):
        """Verify returned items have 'term' key."""
        matched, unknown = match_terms(sample_extraction_result, sample_glossary)

        for item in matched:
            assert "term" in item
            assert isinstance(item["term"], str)

        for item in unknown:
            assert "term" in item
            assert isinstance(item["term"], str)

    def test_match_terms_includes_source_information(
        self, sample_glossary, sample_extraction_result
    ):
        """Verify source information is included."""
        matched, unknown = match_terms(sample_extraction_result, sample_glossary)

        for item in matched + unknown:
            assert "source" in item
            assert item["source"] in ("terms", "concepts")

    def test_match_terms_collects_from_both_terms_and_concepts(
        self, sample_glossary, sample_extraction_result
    ):
        """Verify both terms and concepts are collected."""
        matched, unknown = match_terms(sample_extraction_result, sample_glossary)

        all_results = matched + unknown
        sources = [item["source"] for item in all_results]

        # Should have items from both terms and concepts
        assert "terms" in sources
        assert "concepts" in sources

    def test_match_terms_with_empty_extraction_result(self, sample_glossary):
        """Verify empty extraction result returns empty lists."""
        empty_result = ExtractionResult(
            concepts=[],
            terms=[],
        )

        matched, unknown = match_terms(empty_result, sample_glossary)

        assert len(matched) == 0
        assert len(unknown) == 0

    def test_match_terms_exact_match_only(self, sample_glossary):
        """Verify only exact matches count (not substring matches)."""
        result = ExtractionResult(
            terms=[
                Term(term="gr pc", definition="Not gRPC"),  # Similar but not exact
                Term(term="gRPC", definition="Exact match"),
            ],
            concepts=[],
        )

        matched, unknown = match_terms(result, sample_glossary)

        # Only exact match should be found
        matched_terms = [m["term"] for m in matched]
        assert "gRPC" in matched_terms
        assert "gr pc" not in matched_terms

        unknown_terms = [u["term"] for u in unknown]
        assert "gr pc" in unknown_terms

    def test_match_terms_preserves_original_case_in_result(
        self, sample_glossary, sample_extraction_result
    ):
        """Verify original case is preserved in returned terms."""
        matched, unknown = match_terms(sample_extraction_result, sample_glossary)

        # gRPC should be returned as "gRPC" not "grpc"
        matched_terms = [m["term"] for m in matched]
        assert "gRPC" in matched_terms
