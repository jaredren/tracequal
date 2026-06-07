#!/usr/bin/env python3
"""Methodological validation harness for TraceQual decision extraction.

Compares extraction output against expectations documented in
docs/synthetic_chat_long.md (Notes for fixture users). Output is plain text
suitable for pasting into a methods appendix.

In plain terms: this script runs the decision extractor on a known sample chat,
then checks the extracted "decision matrix" against a list of hand-written
expectations (right number of rows, the right decision types near the right
turns, certain turns correctly skipped, confidence levels behaving sensibly,
etc.). Each expectation prints as PASS / FAIL / PENDING / N/A, and the process
exit code is 1 if anything FAILed (handy for automation), else 0.

Run it from the repository root:

    python3 scripts/validate_extraction.py
    python3 scripts/validate_extraction.py --no-cache       # force a fresh API call
    python3 scripts/validate_extraction.py --fixture docs/other_chat.md
"""

# Treat type hints as plain strings so newer syntax works on older Python.
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass  # decorator that auto-writes boilerplate for data-holding classes
from datetime import datetime, timezone  # for the UTC timestamp in the report header
from enum import Enum  # for the fixed set of check statuses (PASS/FAIL/...)
from pathlib import Path

# Allow running as: python scripts/validate_extraction.py from repo root.
# (Find the repo root two folders up and add it to the import search path.)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tracequal.extractor import (  # noqa: E402
    DEFAULT_MODEL,
    DEFAULT_TEMPERATURE,
    default_cache_path,
    extract_decisions,
    get_prompt_version,
    get_schema_version_from_prompt,
)
from tracequal.parser import parse_chat  # noqa: E402
from tracequal.positioning import extract_positioning  # noqa: E402
from tracequal.schema import DecisionMatrix  # noqa: E402

DEFAULT_FIXTURE = PROJECT_ROOT / "docs" / "synthetic_chat_long.md"

# Matrix rows anchor to AI turns (see prompts/extract_decisions.md). Fixture notes
# sometimes reference researcher turns; checks use a +/-1 turn tolerance window.
TURN_TOLERANCE = 1
# Low bar for a single-fixture demo only; this is not statistically robust.
MIN_CALIBRATION_SAMPLE = 5

# Phrases that suggest a row is documenting a researcher correcting the AI.
# Used to detect rows that SHOULD have been skipped (see _is_correction_row).
CORRECTION_SIGNALS = (
    "actually",
    "wait",
    "not three",
    "four not three",
    "correct",
    "my mistake",
    "miscount",
    "corrected",
)

# For each decision type, the set of turn numbers where we expect to see it.
# Maps a decision label -> a set of reference turn IDs from the fixture notes.
EXPECTED_DECISION_WINDOWS: dict[str, set[int]] = {
    "accepted": {10, 18, 20, 33, 43, 49},
    "modified": {8, 27},
    "rejected": {35, 36},
    "deferred": {16, 17, 37, 38},
    "unclear": {22, 23},
}


# An Enum is a fixed set of named constants. Inheriting from `str` too means
# each member also behaves like its string value (so CheckStatus.PASS == "PASS").
class CheckStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    PENDING = "PENDING"  # check exists but its feature isn't implemented yet
    NA = "N/A"           # descriptive-only, no pass/fail verdict


# @dataclass auto-generates the __init__ and other boilerplate from the fields
# listed below, so CheckResult(check_id=..., status=..., detail=...) just works.
@dataclass
class CheckResult:
    """One validation check outcome (its id, status, and a human-readable detail)."""

    check_id: str
    status: CheckStatus
    detail: str


def _turn_window(center: int) -> set[int]:
    """Return the set of turn IDs within +/-TURN_TOLERANCE of a reference turn."""
    # Set comprehension: for tolerance 1 this yields {center-1, center, center+1}.
    return {center + offset for offset in range(-TURN_TOLERANCE, TURN_TOLERANCE + 1)}


def _rows_at_turns(rows: DecisionMatrix, turn_refs: set[int]) -> DecisionMatrix:
    """Return rows whose turn_id falls within tolerance of any reference turn."""
    # Build one combined set of all acceptable turn IDs (each reference expanded
    # by its tolerance window), then keep rows landing inside it.
    allowed: set[int] = set()
    for ref in turn_refs:
        allowed.update(_turn_window(ref))
    return [row for row in rows if row["turn_id"] in allowed]


def _rows_with_decision_near(
    rows: DecisionMatrix,
    decision: str,
    turn_refs: set[int],
) -> DecisionMatrix:
    """Return rows matching decision near the given turn references."""
    return [
        row
        for row in _rows_at_turns(rows, turn_refs)
        if row["decision"] == decision
    ]


def _is_correction_row(row: dict) -> bool:
    """Return True if the row appears to capture a researcher factual correction.

    Targets exchanges like turns 55-57 where the researcher corrects a numeric
    or factual claim the AI made on the immediately prior turn. Conservative
    heuristic only; false negatives are expected when corrections are implicit.
    """
    if row.get("decision") not in {"modified", "rejected"}:
        return False
    reasoning = str(row.get("reasoning", "")).lower()
    return any(signal in reasoning for signal in CORRECTION_SIGNALS)


def _run_matrix_checks(rows: DecisionMatrix) -> list[CheckResult]:
    """Run all decision-matrix expectations from the synthetic fixture notes.

    Returns a list of CheckResult objects, one per expectation. The pattern
    throughout is: compute something, then append a PASS or FAIL CheckResult.
    """
    results: list[CheckResult] = []

    # Expect the extractor to produce roughly 18-22 rows for this fixture.
    row_count = len(rows)
    if 18 <= row_count <= 22:  # Python allows chained comparisons like this
        results.append(
            CheckResult(
                "matrix_row_count",
                CheckStatus.PASS,
                f"{row_count} rows (expected 18-22)",
            )
        )
    else:
        results.append(
            CheckResult(
                "matrix_row_count",
                CheckStatus.FAIL,
                f"{row_count} rows (expected 18-22)",
            )
        )

    # Expect several "accepted" decisions near the listed turns.
    accepted_near = _rows_with_decision_near(
        rows,
        "accepted",
        {10, 18, 20, 33, 43, 49},
    )
    if len(accepted_near) >= 5:
        results.append(
            CheckResult(
                "decision_enum_accepted",
                CheckStatus.PASS,
                f"Found {len(accepted_near)} 'accepted' rows near expected turns (expected >=5)",
            )
        )
    else:
        results.append(
            CheckResult(
                "decision_enum_accepted",
                CheckStatus.FAIL,
                f"Found {len(accepted_near)} 'accepted' rows near expected turns (expected >=5)",
            )
        )

    modified_near = _rows_with_decision_near(rows, "modified", {8, 27})
    if len(modified_near) >= 2:
        results.append(
            CheckResult(
                "decision_enum_modified",
                CheckStatus.PASS,
                f"Found {len(modified_near)} 'modified' rows near turns 8, 27 (expected >=2)",
            )
        )
    else:
        results.append(
            CheckResult(
                "decision_enum_modified",
                CheckStatus.FAIL,
                f"Found {len(modified_near)} 'modified' rows near turns 8, 27 (expected >=2)",
            )
        )

    rejected_near = _rows_with_decision_near(rows, "rejected", {35, 36})
    if rejected_near:
        results.append(
            CheckResult(
                "decision_enum_rejected",
                CheckStatus.PASS,
                f"Found {len(rejected_near)} 'rejected' row(s) near turns 35-36",
            )
        )
    else:
        results.append(
            CheckResult(
                "decision_enum_rejected",
                CheckStatus.FAIL,
                "No 'rejected' row near turns 35-36",
            )
        )

    deferred_near = _rows_with_decision_near(rows, "deferred", {16, 17, 37, 38})
    if deferred_near:
        results.append(
            CheckResult(
                "decision_enum_deferred",
                CheckStatus.PASS,
                f"Found {len(deferred_near)} 'deferred' row(s) near turns 16-17, 37-38",
            )
        )
    else:
        results.append(
            CheckResult(
                "decision_enum_deferred",
                CheckStatus.FAIL,
                "No 'deferred' row near turns 16-17, 37-38",
            )
        )

    unclear_near = _rows_with_decision_near(rows, "unclear", {22, 23})
    if unclear_near:
        results.append(
            CheckResult(
                "decision_enum_unclear",
                CheckStatus.PASS,
                f"Found {len(unclear_near)} 'unclear' row(s) near turns 22-23",
            )
        )
    else:
        results.append(
            CheckResult(
                "decision_enum_unclear",
                CheckStatus.FAIL,
                "No 'unclear' row near turns 22-23",
            )
        )

    # Collect the distinct decision labels actually present (set comprehension
    # de-duplicates automatically) and confirm all five expected values appear.
    decisions_present = {
        row["decision"] for row in rows
    }
    required = {"accepted", "modified", "rejected", "deferred", "unclear"}
    if required.issubset(decisions_present):
        results.append(
            CheckResult(
                "decision_enum_coverage",
                CheckStatus.PASS,
                "All five decision enum values present",
            )
        )
    else:
        missing = sorted(required - decisions_present)
        results.append(
            CheckResult(
                "decision_enum_coverage",
                CheckStatus.FAIL,
                f"Missing decision values: {', '.join(missing)}",
            )
        )

    # Most rows should be tagged as the "coding" analytic stage for this fixture.
    coding_count = sum(1 for row in rows if row["analytic_stage"] == "coding")
    if coding_count > len(rows) / 2:  # strictly more than half = majority
        results.append(
            CheckResult(
                "analytic_stage_coding_dominant",
                CheckStatus.PASS,
                f"{coding_count}/{len(rows)} rows tagged 'coding' (majority)",
            )
        )
    else:
        results.append(
            CheckResult(
                "analytic_stage_coding_dominant",
                CheckStatus.FAIL,
                f"{coding_count}/{len(rows)} rows tagged 'coding' (expected majority)",
            )
        )

    # The analysis is expected to shift toward "theming" later in the chat
    # (around turn 39+); look for any such rows.
    theming_shift = [
        row for row in rows
        if row["analytic_stage"] == "theming" and row["turn_id"] >= 39
    ]
    if theming_shift:
        turn_ids = sorted({row["turn_id"] for row in theming_shift})
        results.append(
            CheckResult(
                "analytic_stage_theming_shift",
                CheckStatus.PASS,
                f"Theming detected at turn_id(s) {turn_ids} (expected >= turn 39)",
            )
        )
    else:
        results.append(
            CheckResult(
                "analytic_stage_theming_shift",
                CheckStatus.FAIL,
                "No 'theming' row with turn_id >= 39 (phase shift expected around 39-41)",
            )
        )

    # Certain turn ranges are administrative/off-topic and should NOT appear as
    # rows; each "skip_*" check passes only when no rows landed in that range.
    skip_24_26 = _rows_at_turns(rows, {24, 25, 26})
    if not skip_24_26:  # empty list is falsy, meaning correctly skipped
        results.append(
            CheckResult(
                "skip_turns_24_26",
                CheckStatus.PASS,
                "No rows at turn_id 24, 25, or 26",
            )
        )
    else:
        ids = sorted({row["turn_id"] for row in skip_24_26})
        results.append(
            CheckResult(
                "skip_turns_24_26",
                CheckStatus.FAIL,
                f"Unexpected row(s) at turn_id {ids} (administrative exchange)",
            )
        )

    skip_45_46 = _rows_at_turns(rows, {45, 46})
    if not skip_45_46:
        results.append(
            CheckResult(
                "skip_turns_45_46",
                CheckStatus.PASS,
                "No rows at turn_id 45 or 46",
            )
        )
    else:
        ids = sorted({row["turn_id"] for row in skip_45_46})
        results.append(
            CheckResult(
                "skip_turns_45_46",
                CheckStatus.FAIL,
                f"Unexpected row(s) at turn_id {ids} (out-of-scope skip)",
            )
        )

    skip_58_59 = _rows_at_turns(rows, {58, 59})
    if not skip_58_59:
        results.append(
            CheckResult(
                "skip_turns_58_59",
                CheckStatus.PASS,
                "No rows at turn_id 58 or 59",
            )
        )
    else:
        ids = sorted({row["turn_id"] for row in skip_58_59})
        results.append(
            CheckResult(
                "skip_turns_58_59",
                CheckStatus.FAIL,
                f"Unexpected row(s) at turn_id {ids} (meta-reflection belongs in positioning pass)",
            )
        )

    # The miscount correction around turns 55-57 should also be skipped.
    correction_rows = [row for row in rows if _is_correction_row(row)]
    if not correction_rows:
        results.append(
            CheckResult(
                "skip_correction_55_57",
                CheckStatus.PASS,
                "No row documents the turn 55-57 miscount correction",
            )
        )
    else:
        ids = sorted({row["turn_id"] for row in correction_rows})
        results.append(
            CheckResult(
                "skip_correction_55_57",
                CheckStatus.FAIL,
                f"Row(s) at turn_id {ids} appear to document miscount correction",
            )
        )

    # Around tricky turns we expect the extractor to report lower confidence.
    low_t36 = [
        row
        for row in _rows_at_turns(rows, {35, 36})
        if row["confidence"] in {"medium", "low"}
    ]
    if low_t36:
        results.append(
            CheckResult(
                "low_confidence_t36",
                CheckStatus.PASS,
                f"Row near turn 36 with confidence {low_t36[0]['confidence']}",
            )
        )
    else:
        results.append(
            CheckResult(
                "low_confidence_t36",
                CheckStatus.FAIL,
                "No medium/low confidence row near turn 36",
            )
        )

    low_t38 = [
        row for row in _rows_at_turns(rows, {37, 38}) if row["confidence"] == "low"
    ]
    if low_t38:
        results.append(
            CheckResult(
                "low_confidence_t38",
                CheckStatus.PASS,
                "Low confidence row near turn 38",
            )
        )
    else:
        results.append(
            CheckResult(
                "low_confidence_t38",
                CheckStatus.FAIL,
                "No low confidence row near turn 38",
            )
        )

    low_unclear_t22 = [
        row
        for row in _rows_at_turns(rows, {22, 23})
        if row["confidence"] == "low" or row["decision"] == "unclear"
    ]
    if low_unclear_t22:
        results.append(
            CheckResult(
                "low_confidence_t22_23",
                CheckStatus.PASS,
                "Low confidence or unclear decision near turns 22-23",
            )
        )
    else:
        results.append(
            CheckResult(
                "low_confidence_t22_23",
                CheckStatus.FAIL,
                "No low confidence or unclear row near turns 22-23",
            )
        )

    return results


def _in_expected_window(turn_id: int, turn_refs: set[int]) -> bool:
    """Return True when turn_id falls in the tolerance window of references."""
    return any(turn_id in _turn_window(ref) for ref in turn_refs)


def _row_matches_fixture_expectation(row: dict) -> bool | None:
    """Return row correctness vs fixture notes; None when row is unlabeled.

    True  = row agrees with the fixture's expected decision/skip rules.
    False = row contradicts them.
    None  = the fixture says nothing about this turn, so we can't judge it.
    """
    turn_id = int(row["turn_id"])
    decision = str(row["decision"])

    # Rows that fall in a skip range, or look like a correction, are "wrong" if
    # they exist at all (the fixture expects no row there).
    if (
        _in_expected_window(turn_id, {24, 25, 26})
        or _in_expected_window(turn_id, {45, 46})
        or _in_expected_window(turn_id, {58, 59})
    ):
        return False
    if _is_correction_row(row):
        return False

    # Which decision label(s) does the fixture expect at this turn? (.items()
    # iterates the dict as (key, value) pairs.)
    matching_expected_decisions = [
        expected_decision
        for expected_decision, refs in EXPECTED_DECISION_WINDOWS.items()
        if _in_expected_window(turn_id, refs)
    ]
    if not matching_expected_decisions:
        return None  # fixture has no expectation here -> unlabeled

    # Row is correct if its decision is among the expected ones for this turn.
    return decision in matching_expected_decisions


def _run_confidence_calibration_checks(rows: DecisionMatrix) -> list[CheckResult]:
    """Check whether derived confidence tracks fixture-aligned row correctness.

    Idea: high-confidence rows should be right more often than low-confidence
    ones. We only consider rows the fixture actually labels (correctness is not
    None), then compare accuracy across confidence buckets.
    """
    # Keep (row, was_it_correct) pairs only for rows we can actually judge.
    evaluable: list[tuple[dict, bool]] = []
    for row in rows:
        correctness = _row_matches_fixture_expectation(row)
        if correctness is not None:
            evaluable.append((row, correctness))

    if not evaluable:
        return [
            CheckResult(
                "confidence_high_correct_count",
                CheckStatus.PENDING,
                "No evaluable rows for confidence calibration on this fixture",
            ),
            CheckResult(
                "confidence_low_wrong_count",
                CheckStatus.PENDING,
                "No evaluable rows for confidence calibration on this fixture",
            ),
            CheckResult(
                "confidence_calibration_signal",
                CheckStatus.PENDING,
                "No evaluable rows for confidence calibration on this fixture",
            ),
        ]

    # Split the evaluable rows into high- and low-confidence buckets.
    high_rows = [(row, ok) for row, ok in evaluable if row["confidence"] == "high"]
    low_rows = [(row, ok) for row, ok in evaluable if row["confidence"] == "low"]

    # `_` is a throwaway name for the row we don't need here; we only count `ok`.
    high_correct = sum(1 for _, ok in high_rows if ok)
    low_wrong = sum(1 for _, ok in low_rows if not ok)

    high_total = len(high_rows)
    low_total = len(low_rows)

    # Accuracy per bucket. `X if cond else None` guards against dividing by zero
    # when a bucket is empty.
    high_rate = (high_correct / high_total) if high_total else None
    low_rate = (sum(1 for _, ok in low_rows if ok) / low_total) if low_total else None

    results: list[CheckResult] = [
        CheckResult(
            "confidence_distribution",
            CheckStatus.NA,
            (
                "Descriptive only: "
                f"high={sum(1 for row in rows if row['confidence'] == 'high')}, "
                f"medium={sum(1 for row in rows if row['confidence'] == 'medium')}, "
                f"low={sum(1 for row in rows if row['confidence'] == 'low')}"
            ),
        ),
        CheckResult(
            "confidence_high_correct_count",
            CheckStatus.NA if high_total else CheckStatus.PENDING,
            (
                f"Descriptive only: {high_correct}/{high_total} high-confidence rows are fixture-correct "
                f"({high_rate:.3f})"
                if high_total
                else "No high-confidence rows in evaluable set"
            ),
        ),
        CheckResult(
            "confidence_low_wrong_count",
            CheckStatus.NA if low_total else CheckStatus.PENDING,
            (
                f"Descriptive only: {low_wrong}/{low_total} low-confidence rows are fixture-wrong "
                f"({(low_wrong / low_total):.3f})"
                if low_total
                else "No low-confidence rows in evaluable set"
            ),
        ),
    ]

    # Refuse to give a calibration verdict if either bucket is too small to be
    # meaningful; report N/A instead.
    if high_total < MIN_CALIBRATION_SAMPLE or low_total < MIN_CALIBRATION_SAMPLE:
        results.append(
            CheckResult(
                "confidence_calibration_signal",
                CheckStatus.NA,
                (
                    "Insufficient data for calibration verdict: "
                    f"high n={high_total}, low n={low_total}, minimum per bucket={MIN_CALIBRATION_SAMPLE}"
                ),
            )
        )
        return results

    if high_rate is None or low_rate is None:
        results.append(
            CheckResult(
                "confidence_calibration_signal",
                CheckStatus.PENDING,
                "Need both high and low confidence rows to evaluate calibration",
            )
        )
        return results

    # The actual calibration test: high-confidence rows should be more accurate.
    if high_rate > low_rate:
        results.append(
            CheckResult(
                "confidence_calibration_signal",
                CheckStatus.PASS,
                (
                    "High-confidence accuracy exceeds low-confidence accuracy "
                    f"({high_rate:.3f} vs {low_rate:.3f})"
                ),
            )
        )
    else:
        results.append(
            CheckResult(
                "confidence_calibration_signal",
                CheckStatus.FAIL,
                (
                    "Confidence signal is not calibrated on this fixture: "
                    f"high-confidence accuracy {high_rate:.3f} <= low-confidence accuracy {low_rate:.3f}"
                ),
            )
        )

    return results


def _run_positioning_checks(
    turns: list,
    rows: DecisionMatrix,
) -> list[CheckResult]:
    """Attempt positioning checks; mark PENDING when the pass is not implemented."""
    # Each tuple is (check_id, turn to look near, expected shift_type).
    expectations: list[tuple[str, int, str]] = [
        ("positioning_reframing_t18", 18, "reframing"),
        ("positioning_broadening_t32", 32, "broadening"),
        ("positioning_reframing_t40", 40, "reframing"),
    ]

    # The positioning pass may not be built yet; if it raises NotImplementedError
    # we report every expectation as PENDING rather than failing.
    try:
        log = extract_positioning(turns, rows)
    except NotImplementedError as exc:
        return [
            CheckResult(
                check_id,
                CheckStatus.PENDING,
                str(exc),
            )
            for check_id, _, _ in expectations
        ]

    results: list[CheckResult] = []
    for check_id, turn_ref, shift_type in expectations:
        matches = [
            entry
            for entry in log
            if entry["turn_id"] in _turn_window(turn_ref)
            and entry["shift_type"] == shift_type
        ]
        if matches:
            results.append(
                CheckResult(
                    check_id,
                    CheckStatus.PASS,
                    f"Found {shift_type} entry near turn {turn_ref}",
                )
            )
        else:
            results.append(
                CheckResult(
                    check_id,
                    CheckStatus.FAIL,
                    f"No {shift_type} entry near turn {turn_ref}",
                )
            )
    return results


def _format_check_line(result: CheckResult) -> str:
    """Format one check result as a single appendix-ready line."""
    status = f"[{result.status.value}]"
    # The `:<10` and `:<32` are format specs that left-align text in a fixed
    # width, so the columns line up neatly in the printed report.
    return f"{status:<10}{result.check_id:<32}{result.detail}"


def _print_report(
    *,
    fixture_path: Path,
    cache_path: Path,
    model: str,
    temperature: float,
    prompt_version: str,
    schema_version: str,
    results: list[CheckResult],
) -> int:
    """Print the validation report and return the process exit code.

    The `*` in the signature forces every argument to be passed by name
    (keyword-only), which makes the call site self-documenting.
    """
    # Current time in UTC, formatted as an ISO-8601 timestamp for the header.
    run_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # Tally each status. `is` compares identity, which is fine for enum members.
    pass_count = sum(1 for r in results if r.status is CheckStatus.PASS)
    fail_count = sum(1 for r in results if r.status is CheckStatus.FAIL)
    pending_count = sum(1 for r in results if r.status is CheckStatus.PENDING)
    na_count = sum(1 for r in results if r.status is CheckStatus.NA)

    print("TraceQual Extraction Validation Report")
    print(f"Fixture: {fixture_path.relative_to(PROJECT_ROOT)}")
    print(
        f"Model: {model} | Temperature: {temperature} | "
        f"Prompt: {prompt_version} | Schema: {schema_version}"
    )
    print(f"Cache: {cache_path.relative_to(PROJECT_ROOT)}")
    print("Turn anchor: matrix rows use AI turn_id (+/-1 tolerance for fixture crosswalk)")
    print(f"Run: {run_time}")
    print()

    for result in results:
        print(_format_check_line(result))

    print()
    print("---")
    total = len(results)
    print(
        f"{total} checks: {pass_count} PASS, {fail_count} FAIL, "
        f"{pending_count} PENDING, {na_count} N/A"
    )
    if pending_count:
        print("Pending implementation: positioning pass (tracequal/positioning.py)")

    # Non-zero exit code signals failure to shells / CI; any FAIL makes it 1.
    exit_code = 1 if fail_count else 0
    print(f"Exit code: {exit_code}")
    return exit_code


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, run extraction, and print the validation report."""
    parser = argparse.ArgumentParser(
        description="Validate TraceQual extraction against the synthetic long fixture.",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=DEFAULT_FIXTURE,
        help="Path to the chat fixture file.",
    )
    parser.add_argument(
        "--cache-path",
        type=Path,
        default=None,
        help="Path to cache extraction output (default: version-aware path under outputs/).",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Force a fresh API call even if cache exists.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Anthropic model ID for extraction.",
    )
    args = parser.parse_args(argv)

    # `a or b` returns the user's --cache-path if given, otherwise the default.
    cache_path = args.cache_path or default_cache_path()
    turns = parse_chat(args.fixture)
    # Run (or load from cache) the extraction. `not args.no_cache` flips the
    # --no-cache flag into the use_cache argument the extractor expects.
    rows = extract_decisions(
        turns,
        cache_path=cache_path,
        use_cache=not args.no_cache,
        model=args.model,
        temperature=DEFAULT_TEMPERATURE,
    )

    # Run all three groups of checks; .extend appends a whole list at once.
    results = _run_matrix_checks(rows)
    results.extend(_run_confidence_calibration_checks(rows))
    results.extend(_run_positioning_checks(turns, rows))

    return _print_report(
        fixture_path=args.fixture,
        cache_path=cache_path,
        model=args.model,
        temperature=DEFAULT_TEMPERATURE,
        prompt_version=get_prompt_version(),
        schema_version=get_schema_version_from_prompt(),
        results=results,
    )


# Run main() only when this file is executed directly (not imported). SystemExit
# turns main()'s return value into the program's exit code.
if __name__ == "__main__":
    raise SystemExit(main())
