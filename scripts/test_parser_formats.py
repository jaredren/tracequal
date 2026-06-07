#!/usr/bin/env python3
"""Test parse_chat against real Claude and ChatGPT export fixtures.

This is a small, self-contained test runner (not pytest). It feeds two real
chat-export JSON files through the project's parse_chat function and prints a
plain-text PASS/FAIL report describing whether each export parsed correctly and
matched the turn-count / speaker expectations from the MP2 brief.

Run it from the repository root:

    python3 scripts/test_parser_formats.py

The export files live under fixtures/real_exports/ and are gitignored, so they
must exist locally for the tests to actually parse anything.
"""

# Treat type hints as plain text so newer syntax (e.g. `list[str]`) works on
# older Python versions too.
from __future__ import annotations

import sys
import traceback  # used to capture a full stack trace when parsing fails
from pathlib import Path

# Find the repo root (two folders up from this script) and add it to the import
# search path so `import tracequal...` works regardless of the current folder.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Imported after the sys.path tweak, hence the linter-silencing noqa comment.
# `Turn` is the type for one parsed message; `parse_chat` does the parsing.
from tracequal.parser import Turn, parse_chat  # noqa: E402

# The two fixture files we test, bundled in a tuple (an immutable list).
REAL_EXPORTS_DIR = PROJECT_ROOT / "fixtures" / "real_exports"
EXPORT_FILES = (
    REAL_EXPORTS_DIR / "claude_export.json",
    REAL_EXPORTS_DIR / "chatgpt_export.json",
)

# Parser assumption labels for failure diagnosis.
ASSUMPTION_TOP_LEVEL = "(1) top-level container"
ASSUMPTION_MESSAGE_KEY = "(2) message key name"
ASSUMPTION_SPEAKER_PATH = "(3) speaker field path"
ASSUMPTION_TEXT_LOCATION = "(4) text field type/location"


def _classify_parse_failure(error: Exception) -> str:
    """Map parser exceptions to the four format-assumption categories.

    When parsing crashes, this inspects the error text to guess WHICH parser
    assumption was violated, making failures easier to diagnose.
    """
    # Lowercase the error message once so the substring checks are case-insensitive.
    message = str(error).lower()
    if "unsupported json transcript list format" in message:
        return (
            f"{ASSUMPTION_TOP_LEVEL}; {ASSUMPTION_MESSAGE_KEY} "
            "(list wrapper present, but inner object uses neither chat_messages nor messages)"
        )
    if "unsupported json transcript format" in message:
        return f"{ASSUMPTION_TOP_LEVEL}; {ASSUMPTION_MESSAGE_KEY}"
    if "unknown sender" in message or "unknown role" in message:
        return ASSUMPTION_SPEAKER_PATH
    if "json" in message and "decode" in message:
        return ASSUMPTION_TOP_LEVEL
    return (
        f"{ASSUMPTION_TOP_LEVEL} (or downstream); see error: {error}"
    )


def _speaker_sequence(turns: list[Turn]) -> str:
    """Return comma-separated speaker labels in turn order."""
    return ", ".join(turn["speaker"] for turn in turns)


def _malformed_turn_lines(turns: list[Turn]) -> list[str]:
    """Return human-readable notes for empty or malformed turn text."""
    issues: list[str] = []
    for turn in turns:
        # .get(key, default) reads "content" but returns "" if the key is absent,
        # avoiding a KeyError.
        content = turn.get("content", "")
        # isinstance checks the runtime type; content should be a string.
        if not isinstance(content, str):
            issues.append(
                f"turn_id {turn['turn_id']}: content is not a string ({type(content).__name__})"
            )
        elif not content.strip():
            issues.append(f"turn_id {turn['turn_id']}: empty or whitespace-only text")
    return issues


def _expected_alternating_researcher_assistant(turns: list[Turn]) -> bool:
    """Return True when speakers alternate researcher/assistant from turn 1."""
    if not turns:  # an empty list cannot alternate
        return False
    expected = "researcher"  # turn 1 should be the researcher
    for turn in turns:
        if turn["speaker"] != expected:
            return False
        # Flip the expected speaker for the next turn (ternary expression).
        expected = "assistant" if expected == "researcher" else "researcher"
    return True


def _evaluate_expectations(path: Path, turns: list[Turn]) -> list[str]:
    """Apply file-specific expectations described in the MP2 brief."""
    lines: list[str] = []
    name = path.name  # just the filename, e.g. "claude_export.json"

    # Each export format has its own expected turn count / speaker mix.
    if name == "claude_export.json":
        ok_count = len(turns) == 8  # this fixture should yield exactly 8 turns
        lines.append(
            "[PASS]    expect_8_turns                "
            if ok_count
            else "[FAIL]    expect_8_turns                "
            f"got {len(turns)}, expected 8"
        )
        # `sum(1 for ... if ...)` is a common idiom to COUNT items matching a
        # condition: it adds 1 for every matching turn.
        ok_speakers = (
            sum(1 for t in turns if t["speaker"] == "researcher") == 4
            and sum(1 for t in turns if t["speaker"] == "assistant") == 4
        )
        lines.append(
            "[PASS]    expect_4_each_speaker         "
            if ok_speakers
            else "[FAIL]    expect_4_each_speaker         "
            "expected 4 researcher and 4 assistant"
        )
        ok_alt = _expected_alternating_researcher_assistant(turns)
        lines.append(
            "[PASS]    expect_alternating            "
            if ok_alt
            else "[FAIL]    expect_alternating            "
            "expected researcher/assistant alternation"
        )
        return lines

    if name == "chatgpt_export.json":
        # ChatGPT exports include extra nodes (a system message and a null root)
        # that the parser should drop, leaving 8 substantive turns.
        ok_count = len(turns) == 8
        lines.append(
            "[PASS]    expect_8_substantive_turns    "
            if ok_count
            else "[FAIL]    expect_8_substantive_turns    "
            f"got {len(turns)}, expected 8 (after dropping system and null root)"
        )
        # A count of 9 or 10 is a tell-tale sign the system/root nodes leaked in.
        if len(turns) in {9, 10}:
            lines.append(
                "[FAIL]    system_or_root_not_skipped  "
                f"got {len(turns)} turns; likely system node and/or null root included"
            )
        else:
            lines.append(
                "[PASS]    system_or_root_not_skipped  "
                "turn count is not 9 or 10"
            )
        ok_speakers = (
            sum(1 for t in turns if t["speaker"] == "researcher") == 4
            and sum(1 for t in turns if t["speaker"] == "assistant") == 4
        )
        lines.append(
            "[PASS]    expect_4_each_speaker         "
            if ok_speakers
            else "[FAIL]    expect_4_each_speaker         "
            "expected 4 researcher (user) and 4 assistant"
        )
        return lines

    return lines


def _evaluate_file(path: Path) -> list[str]:
    """Parse one export file and return the report lines describing the result."""
    lines: list[str] = [f"File: {path.relative_to(PROJECT_ROOT)}"]

    # Can't test a file that isn't there.
    if not path.exists():
        lines.append("[FAIL]    parse_status                    File not found")
        return lines

    # try/except runs parse_chat and catches ANY error so one bad file does not
    # crash the whole report; the error is recorded as a FAIL instead.
    try:
        turns = parse_chat(path)
    except Exception as exc:
        lines.append("[FAIL]    parse_status                    Parse failed")
        lines.append(f"          error                         {type(exc).__name__}: {exc}")
        lines.append(f"          failed_assumptions            {_classify_parse_failure(exc)}")
        lines.append("          traceback")
        # format_exc() returns the full stack trace as one string; we split it
        # into individual lines and indent each for the report.
        for tb_line in traceback.format_exc().strip().splitlines():
            lines.append(f"          {tb_line}")
        if path.name == "chatgpt_export.json":
            lines.append(
                "[FAIL]    expect_8_substantive_turns    "
                "parse failed before turn extraction"
            )
        return lines

    lines.append("[PASS]    parse_status                    Parse succeeded")
    lines.append(f"          turn_count                    {len(turns)}")
    lines.append(f"          speaker_sequence              {_speaker_sequence(turns)}")

    researcher_count = sum(1 for turn in turns if turn["speaker"] == "researcher")
    assistant_count = sum(1 for turn in turns if turn["speaker"] == "assistant")
    lines.append(
        f"          speaker_counts                researcher={researcher_count}, assistant={assistant_count}"
    )

    malformed = _malformed_turn_lines(turns)
    if malformed:  # non-empty list means at least one problem was found
        lines.append("[FAIL]    malformed_turns               Issues detected")
        for issue in malformed:
            lines.append(f"          {issue}")
    else:
        lines.append("[PASS]    malformed_turns               No empty or malformed turn text")

    lines.extend(_evaluate_expectations(path, turns))
    return lines


def main() -> int:
    """Run parser tests and print plain-text report."""
    print("TraceQual Parser Format Test Report")
    print(f"Directory: {REAL_EXPORTS_DIR.relative_to(PROJECT_ROOT)}")
    print("Gitignore: fixtures/real_exports/* (export files not committed)")
    print()

    # Sanity-check that the export files are gitignored (they may contain real
    # chat data and must not be committed).
    gitignore_path = PROJECT_ROOT / ".gitignore"
    gitignore_text = gitignore_path.read_text(encoding="utf-8")
    if "fixtures/real_exports/*" in gitignore_text:
        print("[PASS]    gitignore_real_exports          fixtures/real_exports/* is gitignored")
    else:
        print("[FAIL]    gitignore_real_exports          fixtures/real_exports/* not found in .gitignore")
    print()

    # Evaluate each fixture and print its block of report lines.
    for export_path in EXPORT_FILES:
        for line in _evaluate_file(export_path):
            print(line)
        print()  # blank line between files

    return 0


# Run main() only when executed directly, not when imported. SystemExit turns
# the returned value into the process exit code.
if __name__ == "__main__":
    raise SystemExit(main())
