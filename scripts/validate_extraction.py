#!/usr/bin/env python3
"""Methodological validation harness for TraceQual decision extraction.

Compares extraction output against expectations documented in
docs/synthetic_chat_long.md (Notes for fixture users). Output is plain text
suitable for pasting into a methods appendix.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

# Allow running as: python scripts/validate_extraction.py from repo root.
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

EXPECTED_DECISION_WINDOWS: dict[str, set[int]] = {
    "accepted": {10, 18, 20, 33, 43, 49},
    "modified": {8, 27},
    "rejected": {35, 36},
    "deferred": {16, 17, 37, 38},
    "unclear": {22, 23},
}


class CheckStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    PENDING = "PENDING"
    NA = "N/A"


@dataclass
class CheckResult:
    """One validation check outcome."""

    check_id: str
    status: CheckStatus
    detail: str


def _turn_window(center: int) -> set[int]:
    """Return turn IDs within tolerance of a reference turn."""
    return {center + offset for offset in range(-TURN_TOLERANCE, TURN_TOLERANCE + 1)}


def _rows_at_turns(rows: DecisionMatrix, turn_refs: set[int]) -> DecisionMatrix:
    """Return rows whose turn_id falls within tolerance of any reference turn."""
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
    """Run all decision-matrix expectations from the synthetic fixture notes."""
    results: list[CheckResult] = []

    row_count = len(rows)
    if 18 <= row_count <= 22:
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

    coding_count = sum(1 for row in rows if row["analytic_stage"] == "coding")
    if coding_count > len(rows) / 2:
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

    skip_24_26 = _rows_at_turns(rows, {24, 25, 26})
    if not skip_24_26:
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
    """Return row correctness vs fixture notes; None when row is unlabeled."""
    turn_id = int(row["turn_id"])
    decision = str(row["decision"])

    # Explicit skip expectations.
    if (
        _in_expected_window(turn_id, {24, 25, 26})
        or _in_expected_window(turn_id, {45, 46})
        or _in_expected_window(turn_id, {58, 59})
    ):
        return False
    if _is_correction_row(row):
        return False

    matching_expected_decisions = [
        expected_decision
        for expected_decision, refs in EXPECTED_DECISION_WINDOWS.items()
        if _in_expected_window(turn_id, refs)
    ]
    if not matching_expected_decisions:
        return None

    return decision in matching_expected_decisions


def _run_confidence_calibration_checks(rows: DecisionMatrix) -> list[CheckResult]:
    """Check whether derived confidence tracks fixture-aligned row correctness."""
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

    high_rows = [(row, ok) for row, ok in evaluable if row["confidence"] == "high"]
    low_rows = [(row, ok) for row, ok in evaluable if row["confidence"] == "low"]

    high_correct = sum(1 for _, ok in high_rows if ok)
    low_wrong = sum(1 for _, ok in low_rows if not ok)

    high_total = len(high_rows)
    low_total = len(low_rows)

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
    expectations: list[tuple[str, int, str]] = [
        ("positioning_reframing_t18", 18, "reframing"),
        ("positioning_broadening_t32", 32, "broadening"),
        ("positioning_reframing_t40", 40, "reframing"),
    ]

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
    """Print the validation report and return the process exit code."""
    run_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
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

    cache_path = args.cache_path or default_cache_path()
    turns = parse_chat(args.fixture)
    rows = extract_decisions(
        turns,
        cache_path=cache_path,
        use_cache=not args.no_cache,
        model=args.model,
        temperature=DEFAULT_TEMPERATURE,
    )

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


if __name__ == "__main__":
    raise SystemExit(main())
