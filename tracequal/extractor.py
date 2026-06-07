"""LLM-based extraction of TraceQual decision matrix rows.

"LLM" = Large Language Model (the AI). This module sends the conversation to the
model with instructions to pull out the analytic *decisions* made during it, then
turns the model's text answer into validated, structured data (the decision matrix).
"""

from __future__ import annotations

import json
import os  # to read environment variables (like the API key)
import re
from pathlib import Path

from dotenv import load_dotenv  # loads variables from a .env file into the environment

from tracequal.parser import Turn, format_transcript
from tracequal.schema import DecisionMatrix, load_schema, validate_decision_matrix

# Locate key files/folders relative to this file (see schema.py for the same trick).
PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent
DEFAULT_PROMPT_PATH = PROJECT_ROOT / "prompts" / "extract_decisions.md"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs"
# The prompt template contains this exact marker; we swap in the real transcript.
TRANSCRIPT_PLACEHOLDER = "{{TRANSCRIPT}}"

# Default settings for the API call. See prompts/prompt_changelog.md.
DEFAULT_MODEL = "claude-sonnet-4-6"  # which AI model to use
DEFAULT_MAX_TOKENS = 8192  # cap on how long the model's answer can be
DEFAULT_TEMPERATURE = 0.0  # 0 = as deterministic/repeatable as possible


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
    """Inject formatted transcript text into the extraction prompt template.

    The prompt is a fill-in-the-blank template. Here we fill the blank (the
    {{TRANSCRIPT}} marker) with the actual conversation text.
    """
    template = load_prompt(prompt_path)
    if TRANSCRIPT_PLACEHOLDER not in template:
        raise ValueError(
            f"Prompt template must contain {TRANSCRIPT_PLACEHOLDER!r}."
        )
    transcript = format_transcript(turns)  # turns -> one clean text block
    return template.replace(TRANSCRIPT_PLACEHOLDER, transcript)


def parse_extraction_response(response_text: str) -> DecisionMatrix:
    """Parse a model response into a decision matrix JSON array.

    The model is asked to reply with JSON, but it sometimes wraps it in markdown
    code fences or adds chatter. This cleans that up and extracts the JSON list.
    """
    cleaned = response_text.strip()
    cleaned = _strip_markdown_fences(cleaned)  # remove ```json ... ``` wrappers

    # `try`/`except`: attempt the simple parse first; if it fails, fall back to
    # digging the JSON array out of surrounding noise.
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        payload = json.loads(_extract_json_array(cleaned))

    # The decision matrix must be a list of rows; reject anything else.
    if not isinstance(payload, list):
        raise ExtractionError("Model response must be a JSON array.")

    return payload


def derive_confidence(decision_stated: bool, reasoning_stated: bool) -> str:
    """Return high if both stated, medium if only decision stated, else low.

    We compute a confidence label from two yes/no flags instead of trusting the
    model to rate its own confidence — this makes the rating consistent and rule-based.
    """
    if decision_stated and reasoning_stated:
        return "high"  # both the decision and the reasoning were made explicit
    if decision_stated and not reasoning_stated:
        return "medium"  # decision is clear, but the "why" was not stated
    return "low"  # the decision itself was not explicitly stated


def _apply_derived_confidence(rows: DecisionMatrix) -> DecisionMatrix:
    """Derive and set confidence from decision_stated and reasoning_stated flags.

    Walks every row, checks the two flags exist and are real booleans, then adds a
    computed "confidence" field. We build a new list rather than editing in place.
    """
    updated_rows: DecisionMatrix = []
    for row in rows:
        # Make sure the model gave us the two flags we need.
        if "decision_stated" not in row or "reasoning_stated" not in row:
            raise ExtractionError(
                "Model response missing decision_stated/reasoning_stated boolean fields."
            )
        decision_stated = row["decision_stated"]
        reasoning_stated = row["reasoning_stated"]
        # They must be true/false, not strings like "yes" — guard against that.
        if not isinstance(decision_stated, bool) or not isinstance(reasoning_stated, bool):
            raise ExtractionError(
                "decision_stated and reasoning_stated must be booleans for each row."
            )

        # `dict(row)` makes a shallow copy so we don't mutate the original row.
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

    "Caching" means: save the (expensive) API result to a file so that next time
    we can reuse it instead of paying to call the model again.
    """
    cache = Path(cache_path) if cache_path is not None else None
    # Fast path: if caching is on and we already have a saved result, reuse it.
    if use_cache and cache is not None and cache.exists():
        return load_cached_decisions(cache)

    # Otherwise, build the prompt and actually call the AI model.
    prompt = build_extraction_prompt(turns, prompt_path)
    response_text = _call_anthropic(
        prompt,
        # Priority for which model to use: explicit arg > env var > built-in default.
        model=model or os.getenv("TRACEQUAL_MODEL", DEFAULT_MODEL),
        api_key=api_key,
        max_tokens=max_tokens,
        temperature=temperature,
    )

    # Parse text -> rows, add the confidence field, then check it obeys the schema.
    rows = _apply_derived_confidence(parse_extraction_response(response_text))
    validate_decision_matrix(rows)

    # Save the fresh result so future runs can use the cache fast path above.
    if cache is not None:
        save_cached_decisions(rows, cache)

    return rows


def load_cached_decisions(cache_path: Path | str) -> DecisionMatrix:
    """Load and validate a cached decision matrix JSON file."""
    path = Path(cache_path)
    with path.open(encoding="utf-8") as handle:
        rows = json.load(handle)
    # Re-validate even cached data, in case the file was edited or is out of date.
    validate_decision_matrix(rows)
    return rows


def save_cached_decisions(rows: DecisionMatrix, cache_path: Path | str) -> None:
    """Write a validated decision matrix to disk."""
    path = Path(cache_path)
    # Create the containing folder if it doesn't exist yet (parents=True makes
    # intermediate folders too; exist_ok=True means "don't error if it's there").
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        # indent=2 pretty-prints the JSON; ensure_ascii=False keeps accents/emoji readable.
        json.dump(rows, handle, indent=2, ensure_ascii=False)
        handle.write("\n")  # end the file with a newline (a common convention)


def _call_anthropic(
    prompt: str,
    *,
    model: str,
    api_key: str | None,
    max_tokens: int,
    temperature: float,
) -> str:
    """Send the extraction prompt to Anthropic and return response text."""
    load_dotenv(PROJECT_ROOT / ".env")  # load the API key from the .env file, if present

    # Use the key passed in, or fall back to the ANTHROPIC_API_KEY environment variable.
    resolved_key = api_key or os.getenv("ANTHROPIC_API_KEY")
    if not resolved_key:
        raise ExtractionError(
            "ANTHROPIC_API_KEY is not set. Add it to .env or pass api_key=."
        )

    # Import the SDK lazily (only when we actually call the API) and give a clear
    # message if it isn't installed, instead of a confusing import crash.
    try:
        import anthropic
    except ImportError as exc:
        raise ExtractionError(
            "anthropic package is required. Install with: pip install anthropic"
        ) from exc

    client = anthropic.Anthropic(api_key=resolved_key)  # the API connection object
    message = client.messages.create(  # this is the actual network call to the AI
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}],  # our one user message
    )

    # The reply comes back as a list of "content blocks"; collect the text ones.
    parts: list[str] = []
    for block in message.content:
        # getattr(block, "type", None) safely reads .type, returning None if absent.
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    if not parts:
        raise ExtractionError("Anthropic response contained no text blocks.")
    return "\n".join(parts)


def _strip_markdown_fences(text: str) -> str:
    """Remove optional markdown code fences from a model response.

    Models often wrap JSON like ```json ... ```. These regex substitutions delete
    the opening fence (with optional "json") and the closing fence.
    """
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)  # strip the opening fence
        text = re.sub(r"\s*```$", "", text)  # strip the closing fence
    return text.strip()


def _extract_json_array(text: str) -> str:
    """Extract the first JSON array substring from a noisy model response.

    As a last resort, grab everything between the first "[" and the last "]".
    """
    start = text.find("[")  # index of the first "[" (-1 if not found)
    end = text.rfind("]")  # index of the last "]" (-1 if not found)
    if start == -1 or end == -1 or end <= start:
        raise ExtractionError("Could not locate a JSON array in the model response.")
    return text[start : end + 1]  # slice including the closing bracket


def get_prompt_version(prompt_path: Path | str | None = None) -> str:
    """Read the Prompt version row from the prompt header table.

    The prompt file starts with a small markdown table; we search it for a line
    like "Prompt version | 1.2.0" and pull out the version number.
    """
    template = load_prompt(prompt_path)
    # The pattern matches "Prompt version", a "|", then three dot-separated numbers.
    match = re.search(
        r"Prompt version\s*\|\s*([0-9]+\.[0-9]+\.[0-9]+)",
        template,
    )
    if not match:
        raise ValueError("Could not find prompt version in prompt template.")
    return match.group(1)  # the captured "X.Y.Z" number


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
    """Return the version-aware default cache path for the current prompt.

    The prompt version is baked into the cache filename so different prompt
    versions never overwrite each other's cached results.
    """
    prompt_version = get_prompt_version(prompt_path)
    return DEFAULT_OUTPUT_DIR / f"synthetic_long_decisions__prompt-{prompt_version}.json"


def assert_prompt_schema_alignment(prompt_path: Path | str | None = None) -> None:
    """Raise SchemaVersionError when prompt and JSON schema versions differ.

    A safety check: the schema version named inside the prompt should match the
    actual schema file we load, so the model is told to produce the shape we verify.
    """
    # Imported here (inside the function) to avoid a circular import at module load.
    from tracequal.schema import SchemaVersionError, get_schema_version

    declared_schema_version = get_schema_version_from_prompt(prompt_path)
    schema_version = get_schema_version(load_schema())
    if declared_schema_version != schema_version:
        raise SchemaVersionError(
            f"Prompt schema version {declared_schema_version!r} does not match "
            f"loaded schema {schema_version!r}."
        )
