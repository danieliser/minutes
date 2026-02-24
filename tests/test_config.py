"""Tests for config module."""

import os
import tempfile
from pathlib import Path

import pytest

from minutes.config import (
    DEFAULT_EXTRACTION_PROMPT,
    DEFAULT_SYSTEM_PROMPT,
    Config,
    load_config,
)


class TestConfigDefaults:
    """Test default configuration values."""

    def test_default_config_values(self):
        """Verify default Config dataclass values."""
        config = Config()
        assert config.gateway_model == "qwen3-4b"
        assert config.gateway_url == "http://localhost:8800/v1"
        assert config.system_prompt == DEFAULT_SYSTEM_PROMPT
        assert config.extraction_prompt == DEFAULT_EXTRACTION_PROMPT
        assert config.output_dir == "./output/"
        assert config.glossary_path == ""
        assert config.max_chunk_size == 12000
        assert config.chunk_overlap == 200
        assert config.max_retries == 3
        assert config.verbose is False


class TestLoadConfigDefaults:
    """Test load_config() with no environment variables set."""

    def test_load_config_returns_config_instance(self, monkeypatch):
        """Verify load_config returns a Config instance."""
        for key in [
            "GATEWAY_MODEL",
            "GATEWAY_URL",
            "SYSTEM_PROMPT",
            "EXTRACTION_PROMPT",
            "OUTPUT_DIR",
            "GLOSSARY_PATH",
            "MAX_CHUNK_SIZE",
            "CHUNK_OVERLAP",
            "MAX_RETRIES",
            "VERBOSE",
        ]:
            monkeypatch.delenv(key, raising=False)

        config = load_config()
        assert isinstance(config, Config)

    def test_load_config_default_values(self, monkeypatch):
        """Verify load_config() uses defaults when env vars not set."""
        for key in [
            "GATEWAY_MODEL",
            "GATEWAY_URL",
            "SYSTEM_PROMPT",
            "EXTRACTION_PROMPT",
            "OUTPUT_DIR",
            "GLOSSARY_PATH",
            "MAX_CHUNK_SIZE",
            "CHUNK_OVERLAP",
            "MAX_RETRIES",
            "VERBOSE",
        ]:
            monkeypatch.delenv(key, raising=False)

        config = load_config()
        assert config.gateway_model == "qwen3-4b"
        assert config.gateway_url == "http://localhost:8800/v1"
        assert config.system_prompt == DEFAULT_SYSTEM_PROMPT
        assert config.extraction_prompt == DEFAULT_EXTRACTION_PROMPT
        assert config.output_dir == "./output/"
        assert config.glossary_path == ""
        assert config.max_chunk_size == 12000
        assert config.chunk_overlap == 200
        assert config.max_retries == 3
        assert config.verbose is False


class TestEnvVarOverrides:
    """Test that environment variables override defaults."""

    def test_gateway_model_override(self, monkeypatch):
        """Verify GATEWAY_MODEL env var overrides default."""
        monkeypatch.setenv("GATEWAY_MODEL", "haiku")
        config = load_config()
        assert config.gateway_model == "haiku"

    def test_gateway_url_override(self, monkeypatch):
        """Verify GATEWAY_URL env var overrides default."""
        monkeypatch.setenv("GATEWAY_URL", "http://remote:9000/v1")
        config = load_config()
        assert config.gateway_url == "http://remote:9000/v1"

    def test_output_dir_override(self, monkeypatch):
        """Verify OUTPUT_DIR env var overrides default."""
        monkeypatch.setenv("OUTPUT_DIR", "/custom/output/")
        config = load_config()
        assert config.output_dir == "/custom/output/"

    def test_glossary_path_override(self, monkeypatch):
        """Verify GLOSSARY_PATH env var overrides default."""
        monkeypatch.setenv("GLOSSARY_PATH", "/custom/glossary.yml")
        config = load_config()
        assert config.glossary_path == "/custom/glossary.yml"

    def test_max_chunk_size_override(self, monkeypatch):
        """Verify MAX_CHUNK_SIZE env var overrides default."""
        monkeypatch.setenv("MAX_CHUNK_SIZE", "5000")
        config = load_config()
        assert config.max_chunk_size == 5000

    def test_chunk_overlap_override(self, monkeypatch):
        """Verify CHUNK_OVERLAP env var overrides default."""
        monkeypatch.setenv("CHUNK_OVERLAP", "300")
        config = load_config()
        assert config.chunk_overlap == 300

    def test_max_retries_override(self, monkeypatch):
        """Verify MAX_RETRIES env var overrides default."""
        monkeypatch.setenv("MAX_RETRIES", "5")
        config = load_config()
        assert config.max_retries == 5


class TestPromptFileResolution:
    """Test prompt file path vs inline string resolution."""

    def test_system_prompt_from_file(self, monkeypatch):
        """Verify system prompt loaded from file if path exists."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("Custom system prompt from file")
            temp_path = f.name

        try:
            monkeypatch.setenv("SYSTEM_PROMPT", temp_path)
            config = load_config()
            assert config.system_prompt == "Custom system prompt from file"
        finally:
            os.unlink(temp_path)

    def test_system_prompt_inline_string(self, monkeypatch):
        """Verify system prompt used as inline string if not a file."""
        monkeypatch.setenv("SYSTEM_PROMPT", "This is an inline system prompt")
        config = load_config()
        assert config.system_prompt == "This is an inline system prompt"

    def test_extraction_prompt_from_file(self, monkeypatch):
        """Verify extraction prompt loaded from file if path exists."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("Custom extraction prompt from file")
            temp_path = f.name

        try:
            monkeypatch.setenv("EXTRACTION_PROMPT", temp_path)
            config = load_config()
            assert config.extraction_prompt == "Custom extraction prompt from file"
        finally:
            os.unlink(temp_path)

    def test_extraction_prompt_inline_string(self, monkeypatch):
        """Verify extraction prompt used as inline string if not a file."""
        monkeypatch.setenv("EXTRACTION_PROMPT", "This is an inline extraction prompt")
        config = load_config()
        assert config.extraction_prompt == "This is an inline extraction prompt"

    def test_prompt_file_with_tilde_expansion(self, monkeypatch):
        """Verify ~ is expanded in file paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "prompt.txt"
            test_file.write_text("Tilde expanded prompt")

            original_expanduser = Path.expanduser

            def mock_expanduser(self):
                if str(self).startswith("~"):
                    return Path(tmpdir) / str(self)[2:]
                return original_expanduser(self)

            monkeypatch.setattr(Path, "expanduser", mock_expanduser)
            monkeypatch.setenv("SYSTEM_PROMPT", "~/prompt.txt")
            config = load_config()
            assert config.system_prompt == "Tilde expanded prompt"

    def test_nonexistent_file_treated_as_string(self, monkeypatch):
        """Verify nonexistent file path is treated as literal string."""
        monkeypatch.setenv("SYSTEM_PROMPT", "/nonexistent/path/to/file.txt")
        config = load_config()
        assert config.system_prompt == "/nonexistent/path/to/file.txt"


class TestBoolParsing:
    """Test boolean environment variable parsing."""

    def test_verbose_false_by_default(self, monkeypatch):
        """Verify VERBOSE defaults to False."""
        monkeypatch.delenv("VERBOSE", raising=False)
        config = load_config()
        assert config.verbose is False

    def test_verbose_true_string(self, monkeypatch):
        """Verify VERBOSE=true is parsed as True."""
        monkeypatch.setenv("VERBOSE", "true")
        config = load_config()
        assert config.verbose is True

    def test_verbose_false_string(self, monkeypatch):
        """Verify VERBOSE=false is parsed as False."""
        monkeypatch.setenv("VERBOSE", "false")
        config = load_config()
        assert config.verbose is False

    def test_verbose_1(self, monkeypatch):
        """Verify VERBOSE=1 is parsed as True."""
        monkeypatch.setenv("VERBOSE", "1")
        config = load_config()
        assert config.verbose is True

    def test_verbose_0(self, monkeypatch):
        """Verify VERBOSE=0 is parsed as False."""
        monkeypatch.setenv("VERBOSE", "0")
        config = load_config()
        assert config.verbose is False

    def test_verbose_yes(self, monkeypatch):
        """Verify VERBOSE=yes is parsed as True."""
        monkeypatch.setenv("VERBOSE", "yes")
        config = load_config()
        assert config.verbose is True

    def test_verbose_on(self, monkeypatch):
        """Verify VERBOSE=on is parsed as True."""
        monkeypatch.setenv("VERBOSE", "on")
        config = load_config()
        assert config.verbose is True

    def test_verbose_case_insensitive(self, monkeypatch):
        """Verify VERBOSE parsing is case insensitive."""
        monkeypatch.setenv("VERBOSE", "TRUE")
        config = load_config()
        assert config.verbose is True

        monkeypatch.setenv("VERBOSE", "False")
        config = load_config()
        assert config.verbose is False
