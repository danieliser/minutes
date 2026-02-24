"""Tests for dedup module."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from minutes.dedup import DedupStore


class TestComputeHash:
    """Test SHA-256 content hashing."""

    def test_compute_hash_returns_hex_string(self):
        """Verify compute_hash returns a valid SHA-256 hex string."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DedupStore(tmpdir)
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("hello")

            hash_value = store.compute_hash(str(test_file))
            assert isinstance(hash_value, str)
            assert len(hash_value) == 64  # SHA-256 hex is 64 characters
            assert all(c in "0123456789abcdef" for c in hash_value)

    def test_same_file_same_hash(self):
        """Verify same file content produces same hash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DedupStore(tmpdir)
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("hello world")

            hash1 = store.compute_hash(str(test_file))
            hash2 = store.compute_hash(str(test_file))
            assert hash1 == hash2

    def test_different_files_different_hashes(self):
        """Verify different file content produces different hashes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DedupStore(tmpdir)
            file1 = Path(tmpdir) / "file1.txt"
            file2 = Path(tmpdir) / "file2.txt"
            file1.write_text("content1")
            file2.write_text("content2")

            hash1 = store.compute_hash(str(file1))
            hash2 = store.compute_hash(str(file2))
            assert hash1 != hash2


class TestIsProcessed:
    """Test checking if a hash has been processed."""

    def test_unknown_hash_returns_none(self):
        """Verify is_processed returns None for unknown hash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DedupStore(tmpdir)
            result = store.is_processed("nonexistent_hash_value_12345")
            assert result is None

    def test_known_hash_returns_output_file(self):
        """Verify is_processed returns output_file for known hash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DedupStore(tmpdir)
            test_hash = "abc123def456"
            output_file = "output.md"

            store.record(test_hash, output_file)
            result = store.is_processed(test_hash)
            assert result == output_file

    def test_schema_mismatch_returns_none(self):
        """Verify is_processed returns None when schema version doesn't match."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DedupStore(tmpdir)
            test_hash = "abc123def456"

            # Record with schema 1.0
            store.record(test_hash, "output.md", schema_version="1.0")

            # Query with schema 1.1
            result = store.is_processed(test_hash, schema_version="1.1")
            assert result is None

    def test_matching_schema_returns_output_file(self):
        """Verify is_processed returns output_file when schema matches."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DedupStore(tmpdir)
            test_hash = "abc123def456"

            store.record(test_hash, "output.md", schema_version="2.0")
            result = store.is_processed(test_hash, schema_version="2.0")
            assert result == "output.md"


class TestRecordAndRoundTrip:
    """Test recording and round-trip operations."""

    def test_record_stores_data(self):
        """Verify record() stores hash and output file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DedupStore(tmpdir)
            test_hash = "test_hash_123"
            output_file = "result.md"

            store.record(test_hash, output_file)
            result = store.is_processed(test_hash)
            assert result == output_file

    def test_record_roundtrip(self):
        """Verify record + is_processed round-trip works."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DedupStore(tmpdir)

            # Create a test file and compute its hash
            test_file = Path(tmpdir) / "input.txt"
            test_file.write_text("test content")
            file_hash = store.compute_hash(str(test_file))

            # Record the mapping
            output_path = "output/result.md"
            store.record(file_hash, output_path)

            # Verify it can be retrieved
            retrieved = store.is_processed(file_hash)
            assert retrieved == output_path


class TestSaveLoadPersistence:
    """Test save/load persistence across instances."""

    def test_dedup_store_persists_to_file(self):
        """Verify DedupStore saves to .dedup.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create and populate store
            store1 = DedupStore(tmpdir)
            test_hash = "persistent_hash_123"
            output_file = "persistent_output.md"
            store1.record(test_hash, output_file)

            # Verify file exists
            dedup_file = Path(tmpdir) / ".dedup.json"
            assert dedup_file.exists()

    def test_dedup_store_loads_from_file(self):
        """Verify new DedupStore instance loads existing .dedup.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create and populate first store
            store1 = DedupStore(tmpdir)
            test_hash = "load_test_hash_123"
            output_file = "load_test_output.md"
            store1.record(test_hash, output_file)

            # Create new store instance in same directory
            store2 = DedupStore(tmpdir)

            # Verify data persisted
            result = store2.is_processed(test_hash)
            assert result == output_file

    def test_multiple_records_persist(self):
        """Verify multiple records persist across instances."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # First instance: record multiple hashes
            store1 = DedupStore(tmpdir)
            records = {
                "hash_1": "output_1.md",
                "hash_2": "output_2.md",
                "hash_3": "output_3.md",
            }
            for h, out in records.items():
                store1.record(h, out)

            # Second instance: verify all records exist
            store2 = DedupStore(tmpdir)
            for h, out in records.items():
                assert store2.is_processed(h) == out

    def test_dedup_json_format(self):
        """Verify .dedup.json has correct format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DedupStore(tmpdir)
            test_hash = "format_test_hash"
            store.record(test_hash, "output.md", schema_version="1.5")

            # Read raw JSON file
            dedup_file = Path(tmpdir) / ".dedup.json"
            with open(dedup_file) as f:
                data = json.load(f)

            # Verify structure
            assert test_hash in data
            assert data[test_hash]["output_file"] == "output.md"
            assert data[test_hash]["schema_version"] == "1.5"


class TestAtomicSave:
    """Test atomic save operations."""

    def test_tmp_file_cleaned_up_after_save(self):
        """Verify .tmp file doesn't linger after save."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DedupStore(tmpdir)
            store.record("test_hash", "output.md")

            # Check that .tmp file doesn't exist
            tmp_file = Path(tmpdir) / ".dedup.tmp"
            assert not tmp_file.exists()

    def test_dedup_file_exists_after_save(self):
        """Verify .dedup.json file exists after save."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DedupStore(tmpdir)
            store.record("test_hash", "output.md")

            dedup_file = Path(tmpdir) / ".dedup.json"
            assert dedup_file.exists()

    def test_no_tmp_file_after_multiple_saves(self):
        """Verify .tmp file doesn't linger after multiple saves."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DedupStore(tmpdir)

            # Multiple saves
            for i in range(5):
                store.record(f"hash_{i}", f"output_{i}.md")

            # Check no .tmp files remain
            tmp_file = Path(tmpdir) / ".dedup.tmp"
            assert not tmp_file.exists()
