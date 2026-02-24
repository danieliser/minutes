"""SHA-256 content hashing and dedup store backed by .dedup.json."""

import hashlib
import json
import os
from pathlib import Path


class DedupStore:
    """SHA-256 content hashing and dedup store backed by .dedup.json."""

    def __init__(self, output_dir: str):
        self.store_path = Path(output_dir) / ".dedup.json"
        self._store: dict[str, dict] = {}
        self._load()

    def _load(self):
        """Load dedup store from .dedup.json if it exists."""
        if self.store_path.exists():
            with open(self.store_path) as f:
                self._store = json.load(f)

    def compute_hash(self, file_path: str) -> str:
        """Compute identity hash from file path + mtime + size.

        Uses stat metadata instead of reading file content, which is faster
        for large files and correctly detects growth (e.g., resumed sessions
        appending to a JSONL transcript).

        Args:
            file_path: Path to the file to hash.

        Returns:
            Hexadecimal SHA-256 hash string.
        """
        p = Path(file_path).resolve()
        stat = p.stat()
        identity = f"{p}:{stat.st_mtime_ns}:{stat.st_size}"
        return hashlib.sha256(identity.encode()).hexdigest()

    def is_processed(self, file_hash: str, schema_version: str = "1.0") -> str | None:
        """Check if a file hash has been processed.

        Args:
            file_hash: SHA-256 hash of the file content.
            schema_version: Schema version to match (default "1.0").

        Returns:
            Output file path if hash exists and schema matches, None otherwise.
        """
        entry = self._store.get(file_hash)
        if entry and entry.get("schema_version") == schema_version:
            return entry["output_file"]
        return None

    def record(self, file_hash: str, output_file: str, schema_version: str = "1.0",
               input_file: str = ""):
        """Record a file hash and its output file.

        Args:
            file_hash: SHA-256 hash of the file identity.
            output_file: Path to the output file.
            schema_version: Schema version (default "1.0").
            input_file: Path to the source input file.
        """
        self._store[file_hash] = {
            "output_file": output_file,
            "schema_version": schema_version,
            "input_file": str(Path(input_file).resolve()) if input_file else "",
        }
        self.save()

    def find_by_input(self, input_file: str) -> str | None:
        """Find existing output for an input file path (any hash version).

        Used to locate previous extraction output when re-processing a file
        that has changed (e.g., resumed session with new messages).

        Args:
            input_file: Path to the source input file.

        Returns:
            Output file path if found, None otherwise.
        """
        resolved = str(Path(input_file).resolve())
        for entry in self._store.values():
            if entry.get("input_file") == resolved:
                return entry["output_file"]
        return None

    def save(self):
        """Save dedup store to .dedup.json using atomic write.

        Uses temp file + rename to ensure atomicity.
        """
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write: write to temp, then rename
        tmp = self.store_path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(self._store, f, indent=2)
        tmp.rename(self.store_path)
