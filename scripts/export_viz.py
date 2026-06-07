#!/usr/bin/env python3
"""Export static disclosure charts for the GitHub / HTML notebook deliverable.

This script loads a previously-saved "decision matrix" cache (a JSON file of
extracted decisions), turns it into a table, draws several charts, and saves
each chart as a PNG image plus a README listing what was produced.

Run it from the repository root like this:

    python3 scripts/export_viz.py
    python3 scripts/export_viz.py --cache-path outputs/my_cache.json --out-dir /tmp/charts

All command-line options have sensible defaults (see DEFAULT_* below), so you
can run it with no arguments.
"""

# `from __future__ import annotations` makes Python treat type hints (like
# `Path | None`) as plain text instead of evaluating them. This lets us use
# newer typing syntax even on slightly older Python versions.
from __future__ import annotations

import argparse  # builds the command-line interface (the --flags below)
import sys
from pathlib import Path  # pathlib.Path is an object-oriented way to handle file paths

# __file__ is this script's own path. .resolve() makes it absolute, and
# .parent.parent walks up two folders (scripts/ -> repo root) to find the
# project root directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
# sys.path is the list of folders Python searches for imports. We add the
# project root so `import tracequal...` works no matter where we run this from.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# These project imports come after the sys.path tweak above, which is why each
# has a `# noqa: E402` comment telling the linter to allow imports here.
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

import pandas as pd  # noqa: E402  # pandas: builds the DataFrame (table) the charts read from


# Default file locations, built by joining the project root with sub-paths
# using the `/` operator that pathlib provides.
DEFAULT_CACHE = PROJECT_ROOT / "outputs" / "synthetic_long_decisions__prompt-1.0.0.json"
DEFAULT_FIXTURE = PROJECT_ROOT / "docs" / "synthetic_chat_long.md"
DEFAULT_OUT = PROJECT_ROOT / "notebooks" / "viz"


def _max_turn(fixture_path: Path | None) -> int | None:
    """Return the highest turn number in the transcript, or None if unavailable.

    Charts use this to know how far the x-axis (turns) should extend. The
    leading underscore in the name is a convention meaning "internal helper."
    """
    # Bail out early if we have no file or the file does not exist on disk.
    if fixture_path is None or not fixture_path.exists():
        return None
    turns = parse_chat(fixture_path)
    # Generator expression pulls each turn's id; `default=None` avoids an error
    # if the transcript has no turns at all.
    return max((turn["turn_id"] for turn in turns), default=None)


def main(argv: list[str] | None = None) -> int:
    """Parse command-line arguments, render every chart, and write the outputs.

    Returns 0 to signal success (a conventional Unix exit code).
    """
    # argparse reads the command line and produces nicely-validated options,
    # plus an automatic --help message.
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
    # parse_args returns an object whose attributes are the option values,
    # e.g. args.cache_path. Passing argv=None makes it read sys.argv (the real
    # command line); tests can pass a custom list instead.
    args = parser.parse_args(argv)

    # `with ... open(...)` opens the file and guarantees it is closed afterward,
    # even if an error happens. json.load reads the JSON into Python objects.
    with args.cache_path.open(encoding="utf-8") as handle:
        rows = json.load(handle)
    # Turn the raw rows into a pandas DataFrame, then let the project's helper
    # clean/derive the columns the charts expect.
    df = prepare_plot_df(pd.DataFrame(rows))
    # A short, repo-relative label (e.g. "outputs/...json") for the report text.
    cache_label = str(args.cache_path.relative_to(PROJECT_ROOT))
    schema_version = infer_schema_version(rows)
    n = len(df)  # number of decision rows, used in provenance captions
    max_turn = _max_turn(args.fixture)

    # Map each output filename to the chart object that should be saved there.
    exports = {
        "01_session_timeline.png": chart_session_timeline(df, max_turn=max_turn),
        "02_analytic_stage_strip.png": chart_analytic_stage_strip(df, max_turn=max_turn),
        "03_timeline_with_bands.png": chart_session_timeline_with_stage_strip(
            df, max_turn=max_turn
        ),
        "04_decision_counts.png": chart_decision_counts(df),
        "05_stage_decision_heatmap.png": chart_stage_decision_heatmap(df),
    }

    # The "grounding by confidence" chart needs boolean disclosure columns.
    # Prefer them from the main cache; otherwise fall back to a separate
    # reference cache; otherwise skip that chart entirely.
    grounding_rows, grounding_label = load_grounding_reference_cache()
    # .issubset checks that BOTH column names exist in the DataFrame's columns.
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

    # Create the output folder. parents=True makes any missing parent folders;
    # exist_ok=True means "don't error if it already exists."
    args.out_dir.mkdir(parents=True, exist_ok=True)
    # Build the README/manifest text line by line; we join with newlines later.
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
    # Save each chart to disk and record a bullet for it in the manifest.
    for filename, chart in exports.items():
        output_path = args.out_dir / filename
        export_chart(chart, output_path)
        # titles.get(filename, filename) returns the friendly title, or falls
        # back to the filename itself if no title was defined.
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

    # "\n".join(...) glues all the lines together with newlines into one string,
    # and write_text creates/overwrites the README file with it.
    manifest_path = args.out_dir / "README.md"
    manifest_path.write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")
    print(f"Wrote {manifest_path}")
    return 0


# This block runs only when the file is executed directly (e.g.
# `python3 scripts/export_viz.py`), not when it is imported by another module.
# SystemExit turns main()'s return value into the program's exit code.
if __name__ == "__main__":
    raise SystemExit(main())
