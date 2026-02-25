"""Tests for scripts/pipe-to-automem.py — standalone AutoMem glue script."""

from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Load the script as a module (it's not a package)
SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "pipe-to-automem.py"
spec = importlib.util.spec_from_file_location("pipe_to_automem", SCRIPT_PATH)
pipe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipe)


# --- Fixtures ---

@pytest.fixture()
def items_db(tmp_path):
    """Create a minimal SQLite DB matching take-minutes items schema."""
    db_path = tmp_path / "minutes.db"
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE items (
            id INTEGER PRIMARY KEY,
            session_id TEXT,
            category TEXT,
            content TEXT,
            detail TEXT,
            owner TEXT
        )
    """)
    conn.executemany(
        "INSERT INTO items (session_id, category, content, detail, owner) VALUES (?, ?, ?, ?, ?)",
        [
            ("sess-1", "decision", "Use PostgreSQL for persistence", "Better JSON support", "Daniel"),
            ("sess-1", "action_item", "Set up CI pipeline", None, "Daniel"),
            ("sess-1", "concept", "Event sourcing", "Append-only log of state changes", None),
            ("sess-1", "term", "CQRS", "Command Query Responsibility Segregation", None),
            ("sess-1", "idea", "Add caching layer", "Redis for hot paths", None),
            ("sess-1", "question", "Should we use GraphQL?", "REST works but GraphQL has introspection", None),
        ],
    )
    conn.commit()
    conn.close()
    return str(db_path)


# --- format_content ---

class TestFormatContent:
    def test_decision_with_all_fields(self):
        result = pipe.format_content("decision", "Use PostgreSQL", "Better JSON", "Daniel")
        assert result == "Use PostgreSQL. Rationale: Better JSON. Owner: Daniel"

    def test_decision_no_detail(self):
        result = pipe.format_content("decision", "Use PostgreSQL", "", "Daniel")
        assert result == "Use PostgreSQL. Owner: Daniel"

    def test_action_item(self):
        result = pipe.format_content("action_item", "Set up CI", "", "Daniel")
        assert result == "ACTION: Set up CI. Owner: Daniel"

    def test_concept(self):
        result = pipe.format_content("concept", "Event sourcing", "Append-only log", "")
        assert result == "Event sourcing. Append-only log"

    def test_term(self):
        result = pipe.format_content("term", "CQRS", "Command Query Responsibility Segregation", "")
        assert result == "TERM: CQRS. Command Query Responsibility Segregation"

    def test_idea(self):
        result = pipe.format_content("idea", "Add caching", "Redis for hot paths", "")
        assert result == "Add caching. Redis for hot paths"

    def test_question(self):
        result = pipe.format_content("question", "Should we use GraphQL?", "REST works fine", "")
        assert result == "QUESTION: Should we use GraphQL?. Context: REST works fine"

    def test_unknown_category(self):
        result = pipe.format_content("unknown", "Some content", "", "")
        assert result == "Some content"


# --- build_tags ---

class TestBuildTags:
    def test_basic_tags(self):
        tags = pipe.build_tags("decision", "sess-1", "my-project", "")
        assert tags == ["decision", "session:sess-1", "project:my-project"]

    def test_with_owner(self):
        tags = pipe.build_tags("decision", "sess-1", "my-project", "Daniel")
        assert "owner:daniel" in tags

    def test_owner_stripped(self):
        tags = pipe.build_tags("decision", "sess-1", "my-project", "  Daniel  ")
        assert "owner:daniel" in tags


# --- pipe_session ---

class TestPipeSession:
    def test_skips_when_env_not_set(self, items_db):
        with patch.dict(os.environ, {}, clear=True):
            result = pipe.pipe_session(items_db, "sess-1", "proj")
        assert result["status"] == "skipped"
        assert "not set" in result["reason"]

    def test_skips_when_db_missing(self):
        with patch.dict(os.environ, {"AUTOMEM_ENDPOINT": "http://localhost", "AUTOMEM_API_KEY": "key"}):
            result = pipe.pipe_session("/nonexistent/path.db", "sess-1", "proj")
        assert result["status"] == "skipped"
        assert "not found" in result["reason"]

    def test_skips_when_no_items(self, tmp_path):
        db_path = tmp_path / "empty.db"
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE items (id INTEGER PRIMARY KEY, session_id TEXT,
                category TEXT, content TEXT, detail TEXT, owner TEXT)
        """)
        conn.commit()
        conn.close()
        with patch.dict(os.environ, {"AUTOMEM_ENDPOINT": "http://localhost", "AUTOMEM_API_KEY": "key"}):
            result = pipe.pipe_session(str(db_path), "nonexistent", "proj")
        assert result["status"] == "skipped"

    @patch("urllib.request.urlopen")
    def test_stores_all_items(self, mock_urlopen, items_db):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        with patch.dict(os.environ, {"AUTOMEM_ENDPOINT": "http://localhost:8000", "AUTOMEM_API_KEY": "test-key"}):
            result = pipe.pipe_session(items_db, "sess-1", "my-project")

        assert result["status"] == "complete"
        assert result["stored"] == 6
        assert result["errors"] == 0
        assert mock_urlopen.call_count == 6

    @patch("urllib.request.urlopen")
    def test_counts_errors(self, mock_urlopen, items_db):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("connection refused")

        with patch.dict(os.environ, {"AUTOMEM_ENDPOINT": "http://localhost:8000", "AUTOMEM_API_KEY": "test-key"}):
            result = pipe.pipe_session(items_db, "sess-1", "proj")

        assert result["status"] == "complete"
        assert result["stored"] == 0
        assert result["errors"] == 6

    @patch("urllib.request.urlopen")
    def test_payload_structure(self, mock_urlopen, items_db):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        with patch.dict(os.environ, {"AUTOMEM_ENDPOINT": "http://localhost:8000", "AUTOMEM_API_KEY": "test-key"}):
            pipe.pipe_session(items_db, "sess-1", "proj")

        # Check first call payload (decision)
        first_call = mock_urlopen.call_args_list[0]
        req = first_call[0][0]
        payload = json.loads(req.data)
        assert payload["importance"] == 0.85
        assert "decision" in payload["tags"]
        assert "session:sess-1" in payload["tags"]
        assert payload["metadata"]["source"] == "take-minutes"
        assert req.get_header("Authorization") == "Bearer test-key"
        assert req.get_header("Content-type") == "application/json"


# --- IMPORTANCE_MAP ---

def test_importance_tiers():
    assert pipe.IMPORTANCE_MAP["decision"] > pipe.IMPORTANCE_MAP["action_item"]
    assert pipe.IMPORTANCE_MAP["action_item"] > pipe.IMPORTANCE_MAP["concept"]
    assert pipe.IMPORTANCE_MAP["concept"] > pipe.IMPORTANCE_MAP["term"]
    assert pipe.IMPORTANCE_MAP["term"] > pipe.IMPORTANCE_MAP["idea"]
    assert pipe.IMPORTANCE_MAP["idea"] > pipe.IMPORTANCE_MAP["question"]
