"""Configuration management for minutes CLI."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


# Built-in defaults
DEFAULT_SYSTEM_PROMPT = """You are an expert at analyzing meeting transcripts and strategic planning sessions.
Your job is to extract structured knowledge: decisions, ideas, questions, action items,
concepts, and terminology. Be precise and concise. Only extract items explicitly discussed;
do not infer unstated decisions. For each category, maintain the original context and
attribution where possible."""

DEFAULT_EXTRACTION_PROMPT = """Analyze this transcript and extract structured knowledge.

Respond with ONLY a valid JSON object matching this schema:
{schema}

Transcript:
{transcript}

Be literal; do not embellish or infer."""


def _resolve_prompt(env_var_name: str, default: str) -> str:
    """
    Resolve a prompt value from environment variable.

    If env var is set to a file path that exists, read its contents.
    Otherwise use the string value directly.
    If unset, use the provided default.
    """
    value = os.getenv(env_var_name)
    if value is None:
        return default

    # Check if it's a file path that exists
    path = Path(value).expanduser()
    if path.exists() and path.is_file():
        return path.read_text()

    # Otherwise use the string value directly
    return value


def _parse_bool(value: str | None) -> bool:
    """Parse boolean from environment variable."""
    if value is None:
        return False
    return value.lower() in ("true", "1", "yes", "on")


@dataclass
class Config:
    """Configuration for minutes CLI."""

    gateway_model: str = "qwen3-4b"
    gateway_url: str = "http://localhost:8800/v1"
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    extraction_prompt: str = DEFAULT_EXTRACTION_PROMPT
    output_dir: str = "./output/"
    glossary_path: str = ""
    max_chunk_size: int = 12000
    chunk_overlap: int = 200
    max_retries: int = 3
    verbose: bool = False


def load_config() -> Config:
    """
    Load configuration from environment variables and .env file.

    Returns:
        Config instance with all settings loaded.
    """
    # Load environment variables from .env file
    load_dotenv()

    # Read all config values with defaults
    config = Config(
        gateway_model=os.getenv("GATEWAY_MODEL", "qwen3-4b"),
        gateway_url=os.getenv("GATEWAY_URL", "http://localhost:8800/v1"),
        output_dir=os.getenv("OUTPUT_DIR", "./output/"),
        glossary_path=os.getenv("GLOSSARY_PATH", ""),
        max_chunk_size=int(os.getenv("MAX_CHUNK_SIZE", "12000")),
        chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "200")),
        max_retries=int(os.getenv("MAX_RETRIES", "3")),
        verbose=_parse_bool(os.getenv("VERBOSE")),
    )

    # Resolve prompts (file path vs inline string)
    config.system_prompt = _resolve_prompt("SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT)
    config.extraction_prompt = _resolve_prompt("EXTRACTION_PROMPT", DEFAULT_EXTRACTION_PROMPT)

    return config
