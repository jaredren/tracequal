"""LLM-based extraction of TraceQual decision matrix rows."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv

from tracequal.parser import Turn, format_transcript
from tracequal.schema import DecisionMatrix, load_schema, validate_decision_matrix

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent
DEFAULT_PROMPT_PATH = PROJECT_ROOT / "prompts" / "extract_decisions.md"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs"
TRANSCRIPT_PLACEHOLDER = "{{TRANSCRIPT}}"

# Default set 2026-05-24. See prompts/prompt_changelog.md.
DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 8192
DEFAULT_TEMPERATURE = 0.0


class ExtractionError(RuntimeError):
    """Raised when the model response cannot be parsed or validated."""


def load_prompt(prompt_path: Path | str | None = None) -> str:
    """Load the extraction prompt template from disk."""
    path = Path(prompt_path) if prompt_path is not None else DEFAULT_PROMPT_PATH
    return path.read_text(encoding="utf-8")


def build_extraction_prompt(
    turns: list[Turn],
    prompt_path: Path | str | None = None,
) -> str:
    """Inject formatted transcript text into the extraction prompt template."""
    template = load_prompt(prompt_path)
    if TRANSCRIPT_PLACEHOLDER not in template:
        raise ValueError(
            f"Prompt template must contain {TRANSCRIPT_PLACEHOLDER!r}."
        )
    transcript = format_transcript(turns)
    return template.replace(TRANSCRIPT_PLACEHOLDER, transcript)


def parse_extraction_response(response_text: str) -> DecisionMatrix:
    """Parse a model response into a decision matrix JSON array."""
    cleaned = response_text.strip()
    cleaned = _strip_markdown_fences(cleaned)

    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        payload = json.loads(_extract_json_array(cleaned))

    if not isinstance(payload, list):
        raise ExtractionError("Model response must be a JSON array.")

    return payload


def derive_confidence(decision_stated: bool, reasoning_stated: bool) -> str:
    """Return high if both stated, medium if only decision stated, else low."""
    if decision_stated and reasoning_stated:
        return "high"
    if decision_stated and not reasoning_stated:
        return "medium"
    return "low"


def _apply_derived_confidence(rows: DecisionMatrix) -> DecisionMatrix:
    """Derive and set confidence from decision_stated and reasoning_stated flags."""
    updated_rows: DecisionMatrix = []
    for row in rows:
        if "decision_stated" not in row or "reasoning_stated" not in row:
            raise ExtractionError(
                "Model response missing decision_stated/reasoning_stated boolean fields."
            )
        decision_stated = row["decision_stated"]
        reasoning_stated = row["reasoning_stated"]
        if not isinstance(decision_stated, bool) or not isinstance(reasoning_stated, bool):
            raise ExtractionError(
                "decision_stated and reasoning_stated must be booleans for each row."
            )

        row_with_confidence = dict(row)
        row_with_confidence["confidence"] = derive_confidence(
            decision_stated=decision_stated,
            reasoning_stated=reasoning_stated,
        )
        updated_rows.append(row_with_confidence)
    return updated_rows


def extract_decisions(
    turns: list[Turn],
    prompt_path: Path | str | None = None,
    *,
    model: str | None = None,
    api_key: str | None = None,
    cache_path: Path | str | None = None,
    use_cache: bool = True,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = DEFAULT_TEMPERATURE,
) -> DecisionMatrix:
    """Extract decision matrix rows from parsed transcript turns.

    Calls the Anthropic Messages API unless a valid cache file exists and
    ``use_cache`` is True. Results are validated against
    ``schema/decision_matrix_v1.json``.
    """
    cache = Path(cache_path) if cache_path is not None else None
    if use_cache and cache is not None and cache.exists():
        return load_cached_decisions(cache)

    prompt = build_extraction_prompt(turns, prompt_path)
    response_text = _call_anthropic(
        prompt,
        model=model or os.getenv("TRACEQUAL_MODEL", DEFAULT_MODEL),
        api_key=api_key,
        max_tokens=max_tokens,
        temperature=temperature,
    )

    rows = _apply_derived_confidence(parse_extraction_response(response_text))
    validate_decision_matrix(rows)

    if cache is not None:
        save_cached_decisions(rows, cache)

    return rows


def load_cached_decisions(cache_path: Path | str) -> DecisionMatrix:
    """Load and validate a cached decision matrix JSON file."""
    path = Path(cache_path)
    with path.open(encoding="utf-8") as handle:
        rows = json.load(handle)
    validate_decision_matrix(rows)
    return rows


def save_cached_decisions(rows: DecisionMatrix, cache_path: Path | str) -> None:
    """Write a validated decision matrix to disk."""
    path = Path(cache_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(rows, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def _call_anthropic(
    prompt: str,
    *,
    model: str,
    api_key: str | None,
    max_tokens: int,
    temperature: float,
) -> str:
    """Send the extraction prompt to Anthropic and return response text."""
    load_dotenv(PROJECT_ROOT / ".env")

    resolved_key = api_key or os.getenv("ANTHROPIC_API_KEY")
    if not resolved_key:
        raise ExtractionError(
            "ANTHROPIC_API_KEY is not set. Add it to .env or pass api_key=."
        )

    try:
        import anthropic
    except ImportError as exc:
        raise ExtractionError(
            "anthropic package is required. Install with: pip install anthropic"
        ) from exc

    client = anthropic.Anthropic(api_key=resolved_key)
    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}],
    )

    parts: list[str] = []
    for block in message.content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    if not parts:
        raise ExtractionError("Anthropic response contained no text blocks.")
    return "\n".join(parts)


def _strip_markdown_fences(text: str) -> str:
    """Remove optional markdown code fences from a model response."""
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _extract_json_array(text: str) -> str:
    """Extract the first JSON array substring from a noisy model response."""
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        raise ExtractionError("Could not locate a JSON array in the model response.")
    return text[start : end + 1]


def get_prompt_version(prompt_path: Path | str | None = None) -> str:
    """Read the Prompt version row from the prompt header table."""
    template = load_prompt(prompt_path)
    match = re.search(
        r"Prompt version\s*\|\s*([0-9]+\.[0-9]+\.[0-9]+)",
        template,
    )
    if not match:
        raise ValueError("Could not find prompt version in prompt template.")
    return match.group(1)


def get_schema_version_from_prompt(prompt_path: Path | str | None = None) -> str:
    """Read the Schema version row from the prompt header table."""
    template = load_prompt(prompt_path)
    match = re.search(
        r"Schema version\s*\|\s*([0-9]+\.[0-9]+\.[0-9]+)",
        template,
    )
    if not match:
        raise ValueError("Could not find schema version in prompt template.")
    return match.group(1)


def default_cache_path(prompt_path: Path | str | None = None) -> Path:
    """Return the version-aware default cache path for the current prompt."""
    prompt_version = get_prompt_version(prompt_path)
    return DEFAULT_OUTPUT_DIR / f"synthetic_long_decisions__prompt-{prompt_version}.json"


def assert_prompt_schema_alignment(prompt_path: Path | str | None = None) -> None:
    """Raise SchemaVersionError when prompt and JSON schema versions differ."""
    from tracequal.schema import SchemaVersionError, get_schema_version

    declared_schema_version = get_schema_version_from_prompt(prompt_path)
    schema_version = get_schema_version(load_schema())
    if declared_schema_version != schema_version:
        raise SchemaVersionError(
            f"Prompt schema version {declared_schema_version!r} does not match "
            f"loaded schema {schema_version!r}."
        )
