#!/usr/bin/env python3
"""Export static disclosure charts for the GitHub / HTML notebook deliverable."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tracequal.parser import parse_chat  # noqa: E402
from tracequal.viz import (  # noqa: E402
    chart_analytic_stage_strip,
    chart_decision_counts,
    chart_grounding_by_confidence,
    chart_session_timeline,
    chart_session_timeline_with_stage_strip,
    chart_stage_decision_heatmap,
    export_chart,
    infer_schema_version,
    load_grounding_reference_cache,
    prepare_plot_df,
    provenance_line,
)
import json  # noqa: E402

import pandas as pd  # noqa: E402


DEFAULT_CACHE = PROJECT_ROOT / "outputs" / "synthetic_long_decisions__prompt-1.0.0.json"
DEFAULT_FIXTURE = PROJECT_ROOT / "docs" / "synthetic_chat_long.md"
DEFAULT_OUT = PROJECT_ROOT / "notebooks" / "viz"


def _max_turn(fixture_path: Path | None) -> int | None:
    if fixture_path is None or not fixture_path.exists():
        return None
    turns = parse_chat(fixture_path)
    return max((turn["turn_id"] for turn in turns), default=None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export TraceQual disclosure charts as PNG.")
    parser.add_argument(
        "--cache-path",
        type=Path,
        default=DEFAULT_CACHE,
        help="Primary decision matrix cache JSON.",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=DEFAULT_FIXTURE,
        help="Transcript fixture for turn extent (optional).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT,
        help="Directory for PNG exports.",
    )
    args = parser.parse_args(argv)

    with args.cache_path.open(encoding="utf-8") as handle:
        rows = json.load(handle)
    df = prepare_plot_df(pd.DataFrame(rows))
    cache_label = str(args.cache_path.relative_to(PROJECT_ROOT))
    schema_version = infer_schema_version(rows)
    n = len(df)
    max_turn = _max_turn(args.fixture)

    exports = {
        "01_session_timeline.png": chart_session_timeline(df, max_turn=max_turn),
        "02_analytic_stage_strip.png": chart_analytic_stage_strip(df, max_turn=max_turn),
        "03_timeline_with_bands.png": chart_session_timeline_with_stage_strip(
            df, max_turn=max_turn
        ),
        "04_decision_counts.png": chart_decision_counts(df),
        "05_stage_decision_heatmap.png": chart_stage_decision_heatmap(df),
    }

    grounding_rows, grounding_label = load_grounding_reference_cache()
    if {"decision_stated", "reasoning_stated"}.issubset(df.columns):
        exports["06_grounding_by_confidence.png"] = chart_grounding_by_confidence(df)
        grounding_provenance = provenance_line(cache_label, schema_version, n)
    elif grounding_rows is not None and grounding_label is not None:
        grounding_df = prepare_plot_df(pd.DataFrame(grounding_rows))
        exports["06_grounding_by_confidence.png"] = chart_grounding_by_confidence(
            grounding_df
        )
        grounding_provenance = provenance_line(
            grounding_label,
            infer_schema_version(grounding_rows),
            len(grounding_df),
        )
    else:
        grounding_provenance = None

    args.out_dir.mkdir(parents=True, exist_ok=True)
    manifest_lines = [
        "# TraceQual static chart exports",
        "",
        provenance_line(cache_label, schema_version, n),
        "",
    ]
    titles = {
        "01_session_timeline.png": "Session timeline",
        "02_analytic_stage_strip.png": "Analytic-stage strip",
        "03_timeline_with_bands.png": "Timeline with stage bands (composite)",
        "04_decision_counts.png": "Decision counts (row n per enum value)",
        "05_stage_decision_heatmap.png": "Stage × decision counts (n)",
        "06_grounding_by_confidence.png": "Record grounding by confidence level",
    }
    for filename, chart in exports.items():
        output_path = args.out_dir / filename
        export_chart(chart, output_path)
        manifest_lines.append(f"- `{filename}` — {titles.get(filename, filename)}")
        print(f"Wrote {output_path}")

    if grounding_provenance:
        manifest_lines.extend(
            [
                "",
                "Grounding chart uses a separate reference cache:",
                grounding_provenance,
            ]
        )
    else:
        manifest_lines.extend(
            [
                "",
                "Grounding chart skipped: no boolean fields and no reference cache.",
            ]
        )

    manifest_path = args.out_dir / "README.md"
    manifest_path.write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")
    print(f"Wrote {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
