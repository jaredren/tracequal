"""Altair disclosure charts for TraceQual decision matrices.

This module turns a "decision matrix" (one row per turn, describing whether an
AI suggestion was accepted/modified/rejected, at what analytic stage, and how
well it was grounded in the transcript) into a set of charts.

It uses two main libraries:
- pandas: tabular data handling (the ``DataFrame``, basically an in-memory table).
- altair: a declarative charting library. Instead of drawing pixels, you
  describe how columns map to visual channels (x, y, color, shape) and Altair
  builds the chart spec for you.

The constants below fix the *category order* and *colors* used everywhere, so
every chart shows decisions, stages, and confidence levels consistently.
"""

# ``from __future__ import annotations`` makes all type hints be treated as
# strings (lazy), which lets us write modern hints like ``int | None`` even on
# older Python versions.
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import altair as alt
import pandas as pd

# Hex color for each possible decision outcome (light pastel fills).
DECISION_COLORS = {
    "accepted": "#c6efce",
    "modified": "#ffeb9c",
    "rejected": "#ffc7ce",
    "deferred": "#bdd7ee",
    "unclear": "#e0e0e0",
}

# The fixed left-to-right / top-to-bottom order categories should appear in.
# Charts sort by these lists so the ordering never depends on the data.
DECISION_ORDER = ["accepted", "modified", "rejected", "deferred", "unclear"]
STAGE_ORDER = [
    "familiarization",
    "coding",
    "theming",
    "reviewing",
    "defining",
    "writeup",
]
CONFIDENCE_ORDER = ["high", "medium", "low"]

# Distinct colors for the background "stage bands" drawn behind the timeline.
STAGE_BAND_COLORS = {
    "familiarization": "#90a4ae",  # blue-gray
    "coding": "#64b5f6",  # blue
    "theming": "#ffb74d",  # amber
    "reviewing": "#f06292",  # rose
    "defining": "#ba68c8",  # purple
    "writeup": "#81c784",  # green
}

# "Grounding" describes how much of a record was explicitly present in the
# transcript versus inferred. Order goes best (both stated) to weakest.
GROUNDING_ORDER = [
    "Both stated",
    "Reasoning inferred",
    "Decision inferred",
]

# Green/amber/red traffic-light colors matching the grounding quality above.
GROUNDING_COLORS = {
    "Both stated": "#2e7d32",
    "Reasoning inferred": "#f9a825",
    "Decision inferred": "#c62828",
}

# Pixel heights reused across charts so paired charts line up visually.
KIOSK_PAIR_CHART_HEIGHT = 280
STAGE_STRIP_HEIGHT = 120

# Rule-derived confidence reference for synthetic_long when the displayed cache is v1.0.0.
# ``Path(__file__)`` is this source file; ``.resolve()`` makes it absolute and
# ``.parent.parent`` walks up two folders, then we point at the cache JSON.
# Using ``/`` between Path objects joins path segments (pathlib idiom).
SYNTHETIC_LONG_GROUNDING_CACHE = (
    Path(__file__).resolve().parent.parent
    / "outputs"
    / "synthetic_long_decisions__prompt-1.2.0.json"
)


def infer_schema_version(rows: list[dict[str, Any]]) -> str:
    """Return 1.1.0 when boolean grounding fields are present, else 1.0.0."""
    # ``rows and ...`` short-circuits: only inspect the first row if the list is
    # non-empty. ``.issubset`` checks both field names exist in that row's keys.
    if rows and {"decision_stated", "reasoning_stated"}.issubset(rows[0].keys()):
        return "1.1.0"
    return "1.0.0"


def provenance_line(cache_source: str, schema_version: str, row_count: int) -> str:
    """Single-line provenance string printed above each chart."""
    return f"Source: `{cache_source}` · Schema v{schema_version} · n={row_count} rows"


def prepare_plot_df(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize categoricals to fixed enum order.

    Converts the text columns into pandas "Categorical" columns with an explicit
    ordered list of categories. This guarantees charts/groupings sort by our
    intended order (not alphabetically) and that all categories exist even if
    some never appear in the data.
    """
    # Work on a copy so we never mutate the caller's DataFrame.
    plot_df = df.copy()
    plot_df["decision"] = pd.Categorical(
        plot_df["decision"], categories=DECISION_ORDER, ordered=True
    )
    plot_df["analytic_stage"] = pd.Categorical(
        plot_df["analytic_stage"], categories=STAGE_ORDER, ordered=True
    )
    # The confidence column is optional (older schemas may omit it).
    if "confidence" in plot_df.columns:
        plot_df["confidence"] = pd.Categorical(
            plot_df["confidence"], categories=CONFIDENCE_ORDER, ordered=True
        )
    return plot_df


def _decision_color_scale() -> alt.Scale:
    """Altair color scale mapping each decision name to its fixed color."""
    # ``domain`` = category names, ``range`` = the colors in matching order.
    # The list comprehension pulls colors in DECISION_ORDER so they line up.
    return alt.Scale(
        domain=DECISION_ORDER,
        range=[DECISION_COLORS[decision] for decision in DECISION_ORDER],
    )


def _stage_band_scale() -> alt.Scale:
    """Altair color scale mapping each analytic stage to its band color."""
    return alt.Scale(
        domain=STAGE_ORDER,
        range=[STAGE_BAND_COLORS[stage] for stage in STAGE_ORDER],
    )


def _count_series(series: pd.Series, categories: list[str]) -> pd.DataFrame:
    """Count how often each category appears, as a 2-column DataFrame.

    Returns rows of (category-name, count) including any categories with zero
    occurrences so charts always show the full set.
    """
    # value_counts() tallies each value; reindex() forces the full category set
    # in order, filling missing ones with 0; reset_index() turns the index into
    # a real column so we get a normal two-column table.
    counts = series.value_counts().reindex(categories, fill_value=0).reset_index()
    counts.columns = ["category", "count"]
    # Rename the category column back to the original series name when it has one.
    return counts.rename(columns={"category": series.name or "category"})


def grounding_label(decision_stated: bool, reasoning_stated: bool) -> str:
    """Map boolean flags to a record-grounding label."""
    if decision_stated and reasoning_stated:
        return GROUNDING_ORDER[0]
    if decision_stated:
        return GROUNDING_ORDER[1]
    return GROUNDING_ORDER[2]


def add_grounding_column(df: pd.DataFrame) -> pd.DataFrame:
    """Add transcript-grounding category from decision_stated / reasoning_stated."""
    grounded = df.copy()
    # apply(..., axis=1) runs the lambda once per row, passing the row; here we
    # turn the two boolean flags into a single human-readable grounding label.
    grounded["grounding"] = grounded.apply(
        lambda row: grounding_label(
            bool(row["decision_stated"]),
            bool(row["reasoning_stated"]),
        ),
        axis=1,
    )
    grounded["grounding"] = pd.Categorical(
        grounded["grounding"], categories=GROUNDING_ORDER, ordered=True
    )
    return grounded


def chart_decision_counts(df: pd.DataFrame) -> alt.Chart:
    """Horizontal bar chart of decision counts with n labels."""
    plot_df = prepare_plot_df(df)
    counts = _count_series(plot_df["decision"], DECISION_ORDER)
    counts.columns = ["decision", "count"]

    # In Altair encodings the suffix marks the data type: ``:Q`` quantitative
    # (numbers), ``:N`` nominal (categories). x=count, y=decision gives horizontal bars.
    bars = (
        alt.Chart(counts)
        .mark_bar()
        .encode(
            x=alt.X("count:Q", title="Row count (n)"),
            y=alt.Y("decision:N", sort=DECISION_ORDER, title=None),
            # legend=None hides the color key (the y-axis already names each bar).
            color=alt.Color("decision:N", scale=_decision_color_scale(), legend=None),
            tooltip=["decision", "count"],
        )
    )
    # Reuse the same data to draw the count number just past the end of each bar
    # (dx=3 nudges text 3px right; format="d" prints a plain integer).
    labels = bars.mark_text(align="left", baseline="middle", dx=3).encode(
        text=alt.Text("count:Q", format="d")
    )
    # ``bars + labels`` layers the text on top of the bars into one chart.
    return (
        (bars + labels)
        .properties(height=KIOSK_PAIR_CHART_HEIGHT)
        .configure_axis(grid=False)
    )


def chart_grounding_by_confidence(df: pd.DataFrame) -> alt.Chart:
    """Stacked bar: confidence level by transcript grounding flags."""
    grounded = add_grounding_column(prepare_plot_df(df))
    # Group by both columns and count rows in each (confidence, grounding) pair.
    # observed=False keeps every categorical combination, even empty ones.
    counts = (
        grounded.groupby(["confidence", "grounding"], observed=False)
        .size()
        .reset_index(name="count")
    )
    # Ensure full grid including zeros.
    # MultiIndex.from_product builds every (confidence × grounding) combination,
    # so reindexing fills any missing pair with a count of 0.
    grid = pd.MultiIndex.from_product(
        [CONFIDENCE_ORDER, GROUNDING_ORDER], names=["confidence", "grounding"]
    )
    counts = (
        counts.set_index(["confidence", "grounding"])
        .reindex(grid, fill_value=0)
        .reset_index()
    )
    counts["confidence"] = pd.Categorical(
        counts["confidence"], categories=CONFIDENCE_ORDER, ordered=True
    )
    counts["grounding"] = pd.Categorical(
        counts["grounding"], categories=GROUNDING_ORDER, ordered=True
    )

    bars = (
        alt.Chart(counts)
        .mark_bar()
        .encode(
            x=alt.X("confidence:N", sort=CONFIDENCE_ORDER, title="Record grounding level"),
            # stack="zero" stacks the segments from a zero baseline (a stacked bar).
            y=alt.Y("count:Q", stack="zero", title="Row count (n)"),
            color=alt.Color(
                "grounding:N",
                sort=GROUNDING_ORDER,
                title="Transcript evidence",
                scale=alt.Scale(
                    domain=GROUNDING_ORDER,
                    range=[GROUNDING_COLORS[g] for g in GROUNDING_ORDER],
                ),
            ),
            tooltip=["confidence", "grounding", "count"],
        )
    )
    # Only label non-empty segments. ``counts[counts["count"] > 0]`` is boolean
    # masking: keep rows where the count is positive. dy=-5 lifts text upward.
    labels = (
        alt.Chart(counts[counts["count"] > 0])
        .mark_text(dy=-5)
        .encode(
            x=alt.X("confidence:N", sort=CONFIDENCE_ORDER),
            y=alt.Y("count:Q", stack="zero"),
            text=alt.Text("count:Q", format="d"),
            color=alt.value("#333333"),
        )
    )
    return (
        (bars + labels)
        .properties(height=KIOSK_PAIR_CHART_HEIGHT)
        .configure_axis(grid=False)
        .configure_axisX(labelAngle=0, labelPadding=8)
        .configure_legend(
            orient="bottom",
            direction="horizontal",
            titleAnchor="start",
            labelLimit=0,
            columns=3,
        )
    )


def _turn_extent(df: pd.DataFrame, max_turn: int | None) -> tuple[int, int]:
    """Return the (min, max) turn numbers to use for the x-axis range.

    Honors a caller-supplied ``max_turn`` but never lets it shrink below the
    largest turn actually present in the data.
    """
    min_turn = 1
    # Largest turn in the data, or 1 if the table is empty.
    max_from_rows = int(df["turn_id"].max()) if not df.empty else 1
    # ``max_turn or max_from_rows`` falls back to the data max when max_turn is
    # None/0; the outer max() ensures we never clip below the data's real range.
    upper = max(max_turn or max_from_rows, max_from_rows)
    return min_turn, upper


def _stage_turn_bands(df: pd.DataFrame, max_turn: int | None) -> pd.DataFrame:
    """One band rect per turn; stage carries forward across turns without matrix rows."""
    plot_df = prepare_plot_df(df)
    if plot_df.empty:
        return pd.DataFrame(
            columns=["turn_id", "x", "x2", "y", "y2", "analytic_stage"]
        )

    # Build a lookup of turn_id -> stage, keeping the first row seen per turn.
    stage_by_turn = (
        plot_df.sort_values("turn_id")
        .drop_duplicates("turn_id", keep="first")
        .set_index("turn_id")["analytic_stage"]
    )
    _, upper = _turn_extent(plot_df, max_turn)
    # Start with the earliest turn's stage as the "current" stage.
    current_stage = stage_by_turn.iloc[0] if not stage_by_turn.empty else STAGE_ORDER[0]
    bands: list[dict[str, Any]] = []
    # Walk every turn 1..upper. When a turn has a known stage, update current;
    # otherwise carry the previous stage forward so bands have no gaps.
    for turn_id in range(1, upper + 1):
        if turn_id in stage_by_turn.index:
            current_stage = stage_by_turn.loc[turn_id]
        # Each band is one unit-wide rectangle centered on the turn (x..x2) and
        # spanning the full height (y=0 to y2=1).
        bands.append(
            {
                "turn_id": turn_id,
                "x": turn_id - 0.5,
                "x2": turn_id + 0.5,
                "y": 0,
                "y2": 1,
                "analytic_stage": str(current_stage),
            }
        )
    return pd.DataFrame(bands)


def chart_session_timeline(
    df: pd.DataFrame,
    max_turn: int | None = None,
    *,
    selectable: bool = False,
) -> alt.Chart:
    """Decision points along the turn axis; shape encodes record grounding level.

    When ``selectable`` is True the points become clickable (used in the
    interactive studio); otherwise it renders a plain static timeline.
    """
    # reset_index(drop=True) renumbers rows 0,1,2...; we then store that as
    # ``row_index`` so the interactive selection can refer to individual points.
    plot_df = prepare_plot_df(df).reset_index(drop=True)
    plot_df["row_index"] = plot_df.index
    _, upper = _turn_extent(plot_df, max_turn)

    # Build the encoding as a dict so we can conditionally add channels below.
    encode_kwargs: dict[str, Any] = {
        "x": alt.X(
            "turn_id:Q",
            scale=alt.Scale(domain=[0.5, upper + 0.5], nice=False),
            title="Turn ID",
        ),
        "y": alt.Y("y_pos:Q", axis=None, scale=alt.Scale(domain=[0, 1], nice=False)),
        "color": alt.Color("decision:N", scale=_decision_color_scale(), title="Decision"),
        "shape": alt.Shape(
            "confidence:N",
            sort=CONFIDENCE_ORDER,
            title="Record grounding level",
        ),
        "tooltip": [
            alt.Tooltip("turn_id:Q", title="Turn"),
            alt.Tooltip("decision:N", title="Decision"),
            alt.Tooltip("analytic_stage:N", title="Stage"),
            alt.Tooltip("confidence:N", title="Grounding level"),
            alt.Tooltip("ai_suggestion_summary:N", title="AI suggestion"),
        ],
    }
    # All points sit on a single horizontal line (y fixed at 0.5).
    plot_df["y_pos"] = 0.5

    params: list[Any] = []
    point_size = 260 if selectable else 180
    if selectable:
        # selection_point lets a user click a point; matched rows are tracked by
        # ``row_index``. The alt.condition(...) calls then style selected vs.
        # unselected points differently (white vs. amber stroke, bigger size).
        select = alt.selection_point(fields=["row_index"], name="timeline_select")
        params.append(select)
        encode_kwargs["stroke"] = alt.condition(
            select, alt.value("#ffffff"), alt.value("#e7b24c")
        )
        encode_kwargs["strokeWidth"] = alt.condition(select, alt.value(4), alt.value(2.5))
        encode_kwargs["size"] = alt.condition(select, alt.value(420), alt.value(point_size))

    # ``filled=True`` draws solid markers. For the static chart we set a fixed
    # size here; the selectable chart sets size via the conditional above instead.
    mark_kwargs: dict[str, Any] = {"filled": True}
    if not selectable:
        mark_kwargs["size"] = point_size

    # ``**`` unpacks the dicts as keyword arguments to mark_point()/encode().
    chart = (
        alt.Chart(plot_df)
        .mark_point(**mark_kwargs)
        .encode(**encode_kwargs)
        .properties(
            height=190 if selectable else 160,
            title="Session timeline (shape = record grounding level)",
        )
        .configure_view(strokeWidth=0)
        .configure_axis(
            grid=False,
            labels=False,
            ticks=False,
            domain=False,
            titlePadding=10,
        )
    )
    # Only attach interaction parameters when we actually created a selection.
    if params:
        return chart.add_params(*params)
    return chart


def chart_analytic_stage_strip(df: pd.DataFrame, max_turn: int | None = None) -> alt.Chart:
    """Background bands for analytic stage along the same turn axis."""
    plot_df = prepare_plot_df(df)
    _, upper = _turn_extent(plot_df, max_turn)
    bands = _stage_turn_bands(plot_df, max_turn)

    # mark_rect with x/x2 and y/y2 draws filled rectangles spanning each band.
    return (
        alt.Chart(bands)
        .mark_rect()
        .encode(
            x=alt.X(
                "x:Q",
                title="Turn",
                scale=alt.Scale(domain=[0.5, upper + 0.5], nice=False),
            ),
            x2="x2:Q",
            y=alt.Y(
                "y:Q",
                axis=None,
                scale=alt.Scale(domain=[0, 1], nice=False, zero=False),
            ),
            y2="y2:Q",
            color=alt.Color(
                "analytic_stage:N",
                sort=STAGE_ORDER,
                scale=_stage_band_scale(),
                title="Analytic stage",
            ),
            tooltip=[
                alt.Tooltip("turn_id:Q", title="Turn"),
                alt.Tooltip("analytic_stage:N", title="Stage"),
            ],
        )
        .properties(height=STAGE_STRIP_HEIGHT)
        .configure_view(strokeWidth=0)
        .configure_axis(
            grid=False,
            ticks=True,
            domain=True,
            titlePadding=10,
        )
        .configure_legend(
            orient="bottom",
            direction="horizontal",
            titleAnchor="start",
            labelLimit=0,
        )
    )


def chart_session_timeline_with_stage_strip(
    df: pd.DataFrame,
    max_turn: int | None = None,
) -> alt.Chart:
    """Combined timeline and stage bands (used for static export composite)."""
    plot_df = prepare_plot_df(df)
    _, upper = _turn_extent(plot_df, max_turn)
    bands_df = _stage_turn_bands(plot_df, max_turn)

    # First layer: the colored stage rectangles in the background.
    bands = (
        alt.Chart(bands_df)
        .mark_rect()
        .encode(
            x=alt.X(
                "x:Q",
                title="Turn",
                scale=alt.Scale(domain=[0.5, upper + 0.5], nice=False),
            ),
            x2="x2:Q",
            y=alt.Y(
                "y:Q",
                axis=None,
                scale=alt.Scale(domain=[0, 1], nice=False, zero=False),
            ),
            y2="y2:Q",
            color=alt.Color(
                "analytic_stage:N",
                sort=STAGE_ORDER,
                scale=_stage_band_scale(),
                title="Analytic stage (band)",
            ),
            tooltip=[
                alt.Tooltip("turn_id:Q", title="Turn"),
                alt.Tooltip("analytic_stage:N", title="Stage"),
            ],
        )
    )

    # Second layer: the decision points drawn on top of the bands.
    points = (
        alt.Chart(plot_df)
        .mark_point(filled=True, size=160, stroke="white", strokeWidth=1)
        .encode(
            x=alt.X(
                "turn_id:Q",
                scale=alt.Scale(domain=[0.5, upper + 0.5], nice=False),
                title="Turn ID",
            ),
            y=alt.value(0.5),
            color=alt.Color("decision:N", scale=_decision_color_scale(), title="Decision"),
            shape=alt.Shape(
                "confidence:N",
                sort=CONFIDENCE_ORDER,
                title="Record grounding level",
            ),
            tooltip=[
                alt.Tooltip("turn_id:Q", title="Turn"),
                alt.Tooltip("decision:N", title="Decision"),
                alt.Tooltip("analytic_stage:N", title="Stage"),
                alt.Tooltip("confidence:N", title="Grounding level"),
                alt.Tooltip("ai_suggestion_summary:N", title="AI suggestion"),
            ],
        )
    )

    # alt.layer stacks the two charts (bands underneath, points on top).
    return (
        alt.layer(bands, points)
        .properties(
            height=180,
            title="Session timeline with analytic-stage bands (shape = record grounding level)",
        )
        .configure_view(strokeWidth=0)
        .configure_axis(
            grid=False,
            labels=False,
            ticks=False,
            domain=False,
            titlePadding=10,
        )
    )


def chart_stage_decision_heatmap(df: pd.DataFrame) -> alt.Chart:
    """Count heatmap: analytic stage × decision with n in each cell."""
    plot_df = prepare_plot_df(df)
    # Full stage × decision grid so every cell exists even with no rows.
    grid = pd.MultiIndex.from_product(
        [STAGE_ORDER, DECISION_ORDER], names=["analytic_stage", "decision"]
    )
    # Count rows per (stage, decision), then fill empty cells with 0.
    counts = (
        plot_df.groupby(["analytic_stage", "decision"], observed=False)
        .size()
        .reindex(grid, fill_value=0)
        .reset_index(name="count")
    )
    counts["analytic_stage"] = pd.Categorical(
        counts["analytic_stage"], categories=STAGE_ORDER, ordered=True
    )
    counts["decision"] = pd.Categorical(
        counts["decision"], categories=DECISION_ORDER, ordered=True
    )

    # A heatmap is a grid of rectangles colored by the count (darker = more).
    heatmap = (
        alt.Chart(counts)
        .mark_rect(stroke="white")
        .encode(
            x=alt.X("decision:N", sort=DECISION_ORDER, title="Decision"),
            y=alt.Y("analytic_stage:N", sort=STAGE_ORDER, title="Analytic stage"),
            color=alt.Color(
                "count:Q",
                # Built-in sequential blue color ramp scaled to the counts.
                scale=alt.Scale(scheme="blues"),
                title="Row count (n)",
            ),
            tooltip=["analytic_stage", "decision", "count"],
        )
    )
    # Print the number in each cell. alt.datum.count refers to that cell's value;
    # the condition dims the text to light gray when the count is 0.
    labels = heatmap.mark_text(baseline="middle").encode(
        text=alt.Text("count:Q", format="d"),
        color=alt.condition(alt.datum.count > 0, alt.value("#111111"), alt.value("#bbbbbb")),
    )
    return (
        (heatmap + labels)
        .properties(height=340, title="Stage × decision counts (n)")
        .configure_axis(grid=False)
        .configure_axisX(labelAngle=0, labelPadding=6)
    )


def triage_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Rows flagged for reviewer triage: low grounding level or unclear decision."""
    if df.empty:
        return df
    # Boolean mask: True for any row that is low-grounding OR an unclear decision
    # (``|`` is element-wise OR across the whole column).
    mask = (df["confidence"] == "low") | (df["decision"] == "unclear")
    columns = [
        "turn_id",
        "decision",
        "analytic_stage",
        "confidence",
        "ai_suggestion_summary",
    ]
    # Keep only the columns that actually exist in this DataFrame.
    available = [column for column in columns if column in df.columns]
    # .loc[mask, available] selects matching rows and those columns; then sort.
    return df.loc[mask, available].sort_values("turn_id")


def load_grounding_reference_cache() -> tuple[list[dict[str, Any]] | None, str | None]:
    """Load the v1.1.0 synthetic_long reference cache when present.

    Returns ``(rows, relative_path_string)`` if the cache file exists and holds a
    JSON list, otherwise ``(None, None)`` so callers can gracefully skip it.
    """
    path = SYNTHETIC_LONG_GROUNDING_CACHE
    if not path.exists():
        return None, None
    # ``with`` ensures the file is closed even if json.load raises.
    with path.open(encoding="utf-8") as handle:
        rows = json.load(handle)
    # Guard against a malformed cache that isn't the expected list of records.
    if not isinstance(rows, list):
        return None, None
    # relative_to(...) trims the path back to a short repo-relative string for display.
    return rows, str(path.relative_to(path.parent.parent))


def export_chart(chart: alt.Chart, output_path: Path, scale: float = 2.0) -> None:
    """Write a static PNG from an Altair chart.

    ``scale`` multiplies the resolution (2.0 = roughly double for crisp images).
    """
    # Imported lazily so the heavy renderer is only loaded when exporting.
    import vl_convert as vlc

    # Create the output folder (and parents) if needed; exist_ok avoids errors.
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # chart.to_json() serializes the chart to a Vega-Lite spec, which vl_convert
    # renders into raw PNG bytes that we then write to disk.
    png_data = vlc.vegalite_to_png(chart.to_json(), scale=scale)
    output_path.write_bytes(png_data)
