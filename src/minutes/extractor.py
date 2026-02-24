"""LLM extraction pipeline for structured knowledge from transcripts."""

import json
import logging
import re
from difflib import SequenceMatcher

import openai

from minutes.config import Config
from minutes.models import ExtractionResult

logger = logging.getLogger(__name__)

# --- Post-extraction cleanup ---

_BAD_OWNER_RE = re.compile(
    r"\b(team|lead|committee|panel|board|management|department|division|"
    r"manager|developer|engineer|architect|analyst|reviewer|group)\b",
    re.IGNORECASE,
)

_VALID_OWNER_RE = re.compile(r"^$|^user$|^assistant$|^[A-Z][a-z]+(\s[A-Z][a-z]+)*$")

_FILLER_PATTERNS = [
    re.compile(r"^no (particular|specific|explicit|clear|stated|given|documented)\b", re.I),
    re.compile(r"^not (specified|mentioned|stated|discussed|provided|given|documented)\b", re.I),
    re.compile(r"^none (provided|given|stated|mentioned|specified)\b", re.I),
    re.compile(r"^straightforward\b", re.I),
    re.compile(r"^n/?a$", re.I),
    re.compile(r"^(no|none|n/?a|tbd|unknown|unspecified)$", re.I),
    re.compile(r"^implicit\b", re.I),
    re.compile(r"^(just|simply)\s+(a\s+)?(decision|choice|standard)\b", re.I),
    re.compile(r"no debate", re.I),
    re.compile(r"no (particular |specific )?reason(ing)?\b", re.I),
    re.compile(r"^it'?s (just )?(what|how) we", re.I),
    re.compile(r"^(standard|default|common|obvious) (choice|decision|approach)\b", re.I),
]


def cleanup_result(result: ExtractionResult, transcript: str = "") -> ExtractionResult:
    """Post-extraction cleanup: normalize owners, strip filler, validate dates."""
    for d in result.decisions:
        d.owner = _clean_owner(d.owner)
        d.rationale = _clean_filler(d.rationale)
        if transcript:
            d.rationale = _clean_ungrounded(d.rationale, transcript)
            d.date = _clean_date(d.date, transcript)

    for q in result.questions:
        q.owner = _clean_owner(q.owner)
        q.context = _clean_filler(q.context)
        if transcript:
            q.context = _clean_ungrounded(q.context, transcript)

    for a in result.action_items:
        a.owner = _clean_owner(a.owner)
        if transcript:
            a.deadline = _clean_date(a.deadline, transcript)

    return result


def _clean_owner(value: str) -> str:
    if not value:
        return ""
    if _VALID_OWNER_RE.match(value):
        return value
    if _BAD_OWNER_RE.search(value):
        return ""
    if value == value.lower():
        return ""
    return value


def _clean_filler(value: str) -> str:
    if not value:
        return ""
    for pattern in _FILLER_PATTERNS:
        if pattern.search(value.strip()):
            return ""
    return value


def _clean_ungrounded(value: str, transcript: str) -> str:
    if not value:
        return ""
    value_words = set(w.lower() for w in re.findall(r'\b\w{4,}\b', value))
    if not value_words:
        return value
    transcript_lower = transcript.lower()
    grounded = sum(1 for w in value_words if w in transcript_lower)
    if grounded / len(value_words) < 0.6:
        return ""
    return value


def _clean_date(value: str, transcript: str) -> str:
    if not value:
        return ""
    return value if value in transcript else ""


class GatewayBackend:
    """LLM backend using the model gateway."""

    def __init__(self, model: str = "qwen3-4b", base_url: str = "http://localhost:8800/v1"):
        self.client = openai.OpenAI(base_url=base_url, api_key="not-needed")
        self.model = model

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Generate text using the model gateway.

        Args:
            system_prompt: System context/instructions
            user_prompt: User query

        Returns:
            Generated text response
        """
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content


def get_backend(config: Config) -> tuple[GatewayBackend, str]:
    """Get LLM backend via model gateway.

    Auto-starts the gateway if not running.

    Args:
        config: Configuration object with gateway settings

    Returns:
        Tuple of (backend instance, backend_type string)

    Raises:
        RuntimeError: If gateway cannot be started
    """
    try:
        from model_gateway.server import ensure_gateway_running
        base_url = ensure_gateway_running()
    except ImportError:
        # model-gateway not installed — use configured URL directly
        base_url = config.gateway_url
    except Exception as e:
        logger.warning(f"Gateway auto-start failed: {e}, using configured URL")
        base_url = config.gateway_url

    backend = GatewayBackend(model=config.gateway_model, base_url=base_url)
    print(f"✓ Using gateway ({config.gateway_model} via {base_url})")
    return backend, "gateway"


def extract_json_block(text: str) -> str:
    """Extract JSON from LLM response, handling various formats.

    Handles:
    - ```json ... ``` code blocks
    - ``` ... ``` code blocks
    - Raw JSON without code blocks

    Args:
        text: Response text potentially containing JSON

    Returns:
        Extracted JSON string

    Raises:
        json.JSONDecodeError: If extracted text is invalid JSON
    """
    text = text.strip()

    # Try ```json ... ``` code block
    if "```json" in text:
        start = text.find("```json") + len("```json")
        end = text.find("```", start)
        if end != -1:
            json_str = text[start:end].strip()
            json.loads(json_str)  # Validate
            return json_str

    # Try ``` ... ``` code block
    if "```" in text:
        start = text.find("```") + len("```")
        end = text.find("```", start)
        if end != -1:
            json_str = text[start:end].strip()
            json.loads(json_str)  # Validate
            return json_str

    # Try raw JSON
    json_str = text
    json.loads(json_str)  # Validate
    return json_str


def chunk_transcript(text: str, max_size: int, overlap: int) -> list[str]:
    """Split transcript into overlapping chunks.

    Prefers paragraph boundaries (double newlines) for chunk breaks.

    Args:
        text: Transcript to chunk
        max_size: Target size in characters (approximate)
        overlap: Character overlap between adjacent chunks

    Returns:
        List of text chunks
    """
    if len(text) <= max_size:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        # End position for this chunk
        end = min(start + max_size, len(text))

        # If not at end, try to find paragraph boundary near end
        if end < len(text):
            # Look for paragraph break near the end position
            search_start = max(start, end - max_size // 4)
            para_break = text.rfind("\n\n", search_start, end)

            if para_break != -1 and para_break > start:
                end = para_break + 2  # Include the double newline
            # If no para break in range, use max_size

        chunks.append(text[start:end])

        # Move start position, accounting for overlap
        # Ensure forward progress even with small chunks
        new_start = end - overlap
        if new_start <= start:
            new_start = end  # No overlap if chunk was too small
        start = new_start

    return chunks if chunks else [text]


def merge_results(results: list[ExtractionResult]) -> ExtractionResult:
    """Merge multiple extraction results, deduplicating and selecting best items.

    Deduplication:
    - Decisions/Ideas/Questions/ActionItems: >80% text similarity
    - Concepts/Terms: exact name/term match
    - TLDR: keep longest

    Args:
        results: List of extraction results to merge

    Returns:
        Single merged ExtractionResult
    """
    if not results:
        return ExtractionResult()

    merged = ExtractionResult()

    # Concatenate all lists
    all_decisions = [d for r in results for d in r.decisions]
    all_ideas = [i for r in results for i in r.ideas]
    all_questions = [q for r in results for q in r.questions]
    all_action_items = [a for r in results for a in r.action_items]
    all_concepts = [c for r in results for c in r.concepts]
    all_terms = [t for r in results for t in r.terms]

    # Deduplicate decisions by >80% similarity
    merged.decisions = _deduplicate_by_similarity(all_decisions, attr="summary")

    # Deduplicate ideas by >80% similarity
    merged.ideas = _deduplicate_by_similarity(all_ideas, attr="title")

    # Deduplicate questions by >80% similarity
    merged.questions = _deduplicate_by_similarity(all_questions, attr="text")

    # Deduplicate action_items by >80% similarity
    merged.action_items = _deduplicate_by_similarity(
        all_action_items, attr="description"
    )

    # Cross-category dedup: action_items that restate a decision
    merged.action_items = _cross_category_dedup(
        merged.action_items, "description", merged.decisions, "summary"
    )

    # Cross-category dedup: ideas that restate a decision
    merged.ideas = _cross_category_dedup(
        merged.ideas, "title", merged.decisions, "summary"
    )

    # Deduplicate concepts by exact name match
    merged.concepts = _deduplicate_by_exact_attr(all_concepts, attr="name")

    # Deduplicate terms by exact term match
    merged.terms = _deduplicate_by_exact_attr(all_terms, attr="term")

    # Keep longest TLDR
    tldrs = [r.tldr for r in results if r.tldr]
    merged.tldr = max(tldrs, key=len) if tldrs else ""

    return merged


def _deduplicate_by_similarity(
    items: list, attr: str, threshold: float = 0.8
) -> list:
    """Deduplicate items by >threshold text similarity on an attribute."""
    if not items:
        return []

    kept = []
    for item in items:
        item_text = getattr(item, attr, "")

        is_duplicate = False
        for kept_item in kept:
            kept_text = getattr(kept_item, attr, "")
            similarity = SequenceMatcher(None, item_text, kept_text).ratio()
            if similarity >= threshold:
                is_duplicate = True
                break

        if not is_duplicate:
            kept.append(item)

    return kept


def _cross_category_dedup(
    items: list, items_attr: str,
    reference: list, reference_attr: str,
    threshold: float = 0.8,
) -> list:
    """Remove items that duplicate entries in a reference category."""
    if not items or not reference:
        return items
    ref_texts = [getattr(r, reference_attr, "").lower() for r in reference]
    kept = []
    for item in items:
        item_text = getattr(item, items_attr, "").lower()
        is_dup = any(
            SequenceMatcher(None, item_text, ref).ratio() >= threshold
            for ref in ref_texts
        )
        if not is_dup:
            kept.append(item)
    return kept


def _deduplicate_by_exact_attr(items: list, attr: str) -> list:
    """Deduplicate items by exact attribute match, keeping first occurrence."""
    if not items:
        return []

    seen = set()
    kept = []
    for item in items:
        item_val = getattr(item, attr, "")
        if item_val not in seen:
            seen.add(item_val)
            kept.append(item)

    return kept


def extract_structured(
    backend: GatewayBackend,
    config: Config,
    transcript: str,
) -> ExtractionResult:
    """Extract structured knowledge from transcript using LLM.

    Retries up to config.max_retries times on validation error.
    Returns empty result on final failure.
    """
    schema = ExtractionResult.model_json_schema()

    for attempt in range(config.max_retries):
        try:
            user_prompt = config.extraction_prompt.format(
                schema=json.dumps(schema), transcript=transcript
            )

            response = backend.generate(config.system_prompt, user_prompt)

            json_str = extract_json_block(response)
            data = json.loads(json_str)

            result = ExtractionResult(**data)

            if config.verbose:
                logger.info(
                    f"Extraction successful on attempt {attempt + 1}"
                )

            return result

        except (json.JSONDecodeError, ValueError) as e:
            if config.verbose:
                logger.warning(
                    f"Extraction attempt {attempt + 1} failed: {e}"
                )

            if attempt == config.max_retries - 1:
                if config.verbose:
                    logger.error(
                        f"Extraction failed after {config.max_retries} attempts"
                    )
                return ExtractionResult()

    return ExtractionResult()


def process_transcript(
    backend: GatewayBackend,
    config: Config,
    transcript: str,
) -> ExtractionResult:
    """Process transcript, chunking if necessary and merging results."""
    if not transcript:
        return ExtractionResult()

    if len(transcript) <= config.max_chunk_size:
        result = extract_structured(backend, config, transcript)
        return cleanup_result(result, transcript)

    chunks = chunk_transcript(
        transcript, config.max_chunk_size, config.chunk_overlap
    )

    results = []
    for i, chunk in enumerate(chunks):
        if config.verbose:
            logger.info(f"Processing chunk {i + 1}/{len(chunks)}")

        result = extract_structured(backend, config, chunk)
        results.append(result)

    merged = merge_results(results)
    merged = cleanup_result(merged, transcript)

    if config.verbose:
        logger.info(f"Merged {len(chunks)} chunks into final result")

    return merged
