#!/usr/bin/env python3
"""Test parse_chat against real Claude and ChatGPT export fixtures."""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tracequal.parser import Turn, parse_chat  # noqa: E402

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
    """Map parser exceptions to the four format-assumption categories."""
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
        content = turn.get("content", "")
        if not isinstance(content, str):
            issues.append(
                f"turn_id {turn['turn_id']}: content is not a string ({type(content).__name__})"
            )
        elif not content.strip():
            issues.append(f"turn_id {turn['turn_id']}: empty or whitespace-only text")
    return issues


def _expected_alternating_researcher_assistant(turns: list[Turn]) -> bool:
    """Return True when speakers alternate researcher/assistant from turn 1."""
    if not turns:
        return False
    expected = "researcher"
    for turn in turns:
        if turn["speaker"] != expected:
            return False
        expected = "assistant" if expected == "researcher" else "researcher"
    return True


def _evaluate_expectations(path: Path, turns: list[Turn]) -> list[str]:
    """Apply file-specific expectations described in the MP2 brief."""
    lines: list[str] = []
    name = path.name

    if name == "claude_export.json":
        ok_count = len(turns) == 8
        lines.append(
            "[PASS]    expect_8_turns                "
            if ok_count
            else "[FAIL]    expect_8_turns                "
            f"got {len(turns)}, expected 8"
        )
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
        ok_count = len(turns) == 8
        lines.append(
            "[PASS]    expect_8_substantive_turns    "
            if ok_count
            else "[FAIL]    expect_8_substantive_turns    "
            f"got {len(turns)}, expected 8 (after dropping system and null root)"
        )
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
    """Parse one export and return report lines."""
    lines: list[str] = [f"File: {path.relative_to(PROJECT_ROOT)}"]

    if not path.exists():
        lines.append("[FAIL]    parse_status                    File not found")
        return lines

    try:
        turns = parse_chat(path)
    except Exception as exc:
        lines.append("[FAIL]    parse_status                    Parse failed")
        lines.append(f"          error                         {type(exc).__name__}: {exc}")
        lines.append(f"          failed_assumptions            {_classify_parse_failure(exc)}")
        lines.append("          traceback")
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
    if malformed:
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

    gitignore_path = PROJECT_ROOT / ".gitignore"
    gitignore_text = gitignore_path.read_text(encoding="utf-8")
    if "fixtures/real_exports/*" in gitignore_text:
        print("[PASS]    gitignore_real_exports          fixtures/real_exports/* is gitignored")
    else:
        print("[FAIL]    gitignore_real_exports          fixtures/real_exports/* not found in .gitignore")
    print()

    for export_path in EXPORT_FILES:
        for line in _evaluate_file(export_path):
            print(line)
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
