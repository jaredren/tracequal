"""TraceQual interactive studio — upload or paste a transcript, extract, explore.

This file is one *page* of a Streamlit multi-page app. Streamlit treats any
``.py`` file inside a top-level ``pages/`` folder as a separate page, and shows
it automatically in the sidebar navigation (the leading ``1_`` controls the
ordering and is stripped from the displayed title). The main entry-point script
lives at the project root; this page is reachable from that app's sidebar.

What this page lets a user do:
  1. Provide a researcher-AI coding-session transcript, either by uploading a
     file, pasting text, loading a built-in example, or loading a previously
     saved "matrix" (already-extracted results) JSON file.
  2. Run "extraction" (an LLM call) that turns the raw transcript into a
     structured *decision matrix* — one row per detected decision point.
  3. Explore that matrix through charts and an interactive, filterable table.

Streamlit reruns this entire script top-to-bottom on every user interaction
(every click, text edit, etc.). Because local variables are wiped on each rerun,
anything that must survive between interactions is stored in ``st.session_state``
(a dict-like object that persists for the user's session). That pattern is used
heavily below to remember the parsed transcript, the extracted rows, and any
error messages.
"""

# Lets us use modern type-hint syntax (e.g. ``list[Turn] | None``) on older
# Python versions by deferring evaluation of annotations.
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from tracequal.extractor import (
    DEFAULT_MODEL,
    ExtractionError,
    extract_decisions,
    get_prompt_version,
    get_schema_version_from_prompt,
)
from tracequal.parser import Turn, format_transcript, parse_chat, parse_chat_content
from tracequal.schema import get_schema_version
from tracequal.ui_theme import desc, page_intro, section_heading, section_label, style_chart
from tracequal.viz import (
    DECISION_COLORS,
    chart_analytic_stage_strip,
    chart_decision_counts,
    chart_grounding_by_confidence,
    chart_session_timeline,
    chart_stage_decision_heatmap,
    infer_schema_version,
    load_grounding_reference_cache,
    prepare_plot_df,
    provenance_line,
    triage_rows,
)

# __file__ is this script's path; .resolve() makes it absolute, and going up two
# parent directories (pages/ -> project root) anchors all other paths reliably,
# regardless of where Streamlit is launched from.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCS = PROJECT_ROOT / "docs"

# Built-in example transcripts shown in the sidebar. Maps a human-readable
# label to the file on disk. ``/`` on Path objects joins path segments.
EXAMPLES = {
    "Short demo (11 turns)": DOCS / "tracequal_example_short.md",
    "Long demo (31 turns)": DOCS / "tracequal_example_long.md",
    "Short demo (Claude JSON)": DOCS / "tracequal_example_short.json",
}
# "Simulate upload" demo shortcuts: each entry describes a committed sample file
# that can be loaded with one button click as if the user had uploaded it.
# "key" is a unique id used for Streamlit widget keys (see below).
DEMO_UPLOADS: list[dict[str, str | Path]] = [
    {
        "key": "short_md",
        "label": "Short coding session",
        "filename": "interview_excerpt.md",
        "detail": "11 turns · TraceQual markdown export",
        "path": DOCS / "tracequal_example_short.md",
    },
    {
        "key": "long_md",
        "label": "Long coding session",
        "filename": "remote_workers_transcript.md",
        "detail": "31 turns · thematic analysis sample",
        "path": DOCS / "tracequal_example_long.md",
    },
    {
        "key": "short_json",
        "label": "Claude chat export",
        "filename": "claude_export.json",
        "detail": "11 turns · Claude JSON format",
        "path": DOCS / "tracequal_example_short.json",
    },
    {
        "key": "synthetic_long",
        "label": "Notebook fixture (long)",
        "filename": "synthetic_chat_long.md",
        "detail": "53 turns · validation harness transcript",
        "path": DOCS / "synthetic_chat_long.md",
    },
]
# Pre-computed extraction results committed to the repo. Loading these lets the
# app show a full matrix without making a (slow, paid) LLM call.
CACHED_LONG = PROJECT_ROOT / "outputs" / "tracequal_example_long__prompt-1.0.0.json"
CACHED_SYNTHETIC_LONG = PROJECT_ROOT / "outputs" / "synthetic_long_decisions__prompt-1.0.0.json"
SYNTHETIC_FIXTURE = DOCS / "synthetic_chat_long.md"


def _init_state() -> None:
    """Seed ``st.session_state`` with default values on first run.

    Streamlit reruns this script on every interaction, so we only set a key if
    it is missing — that way existing values entered earlier are preserved.
    """
    defaults = {
        "turns": None,
        "rows": None,
        "source_label": "",
        "cache_source": "",
        "parse_error": None,
        "extract_error": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _parse_upload(uploaded) -> tuple[list[Turn] | None, str | None]:
    """Turn an uploaded file into a list of conversation turns.

    ``uploaded`` is Streamlit's UploadedFile object (the return value of
    ``st.file_uploader``). We pick a parser based on the file extension.
    Returns the parsed turns and the original filename.
    """
    suffix = Path(uploaded.name).suffix.lower()
    # .getvalue() returns the raw uploaded bytes; decode them to a text string.
    text = uploaded.getvalue().decode("utf-8")
    if suffix == ".json":
        turns = parse_chat_content(text, format="json")
    elif suffix in {".md", ".txt"}:
        turns = parse_chat_content(text, format="text")
    else:
        raise ValueError("Unsupported file type. Upload .json, .md, or .txt.")
    return turns, uploaded.name


def _parse_path(path: Path) -> tuple[list[Turn], str]:
    """Parse a transcript file on disk, returning the turns and a short label.

    The label is the path made relative to the project root, so it reads nicely
    in the UI instead of showing the full absolute path.
    """
    return parse_chat(path), str(path.relative_to(PROJECT_ROOT))


def _load_transcript(path: Path, source_label: str) -> None:
    """Parse a transcript file and store it in session state as the active one.

    Resets any previously extracted rows and error messages so the UI starts
    fresh for this newly loaded transcript.
    """
    turns, _ = _parse_path(path)
    st.session_state.turns = turns
    st.session_state.rows = None
    st.session_state.source_label = source_label
    st.session_state.cache_source = ""
    st.session_state.parse_error = None
    st.session_state.extract_error = None


def _simulate_upload(path: Path, filename: str) -> None:
    """Load a committed fixture as if the user uploaded filename."""
    _load_transcript(path, filename)


def _render_simulated_upload_buttons() -> None:
    """Draw a row of one-click buttons that load the DEMO_UPLOADS samples."""
    section_label("Simulate upload")
    desc(
        "Demo shortcuts — loads a sample transcript as if it were uploaded here. "
        "No file picker needed."
    )
    # st.columns(n) splits the page into n side-by-side layout columns. We make
    # one column per demo so the buttons sit in a single horizontal row.
    cols = st.columns(len(DEMO_UPLOADS))
    # Pair each column with its demo; strict=True asserts the lists are equal
    # length (they always are, since cols was built from DEMO_UPLOADS).
    for column, demo in zip(cols, DEMO_UPLOADS, strict=True):
        # "with column:" routes the widgets inside it into that column.
        with column:
            # Render the demo's title/detail as raw HTML (unsafe_allow_html lets
            # Streamlit emit our HTML instead of escaping it as plain text).
            st.markdown(
                f'<p class="app-demo-label">{demo["label"]}</p>'
                f'<p class="app-demo-detail">{demo["detail"]}</p>',
                unsafe_allow_html=True,
            )
            # st.button returns True only on the rerun triggered by its click.
            # A unique "key" is required so Streamlit can tell the buttons apart.
            if st.button(
                f"Upload {demo['filename']}",
                key=f"simulate_{demo['key']}",
                use_container_width=True,
            ):
                _simulate_upload(Path(demo["path"]), str(demo["filename"]))
                # Force an immediate rerun so the loaded transcript shows now.
                st.rerun()
    st.divider()


def _style_matrix(df: pd.DataFrame):
    """Return a pandas Styler that color-codes the ``decision`` column.

    A pandas Styler describes cell formatting without altering the data; Streamlit
    can render it directly. ``.map`` applies a function per cell that returns a
    CSS string, here limited (``subset``) to the "decision" column.
    """
    def _color_decision(value: str) -> str:
        # Look up a background color for this decision type; empty means none.
        color = DECISION_COLORS.get(value, "")
        return f"background-color: {color}" if color else ""

    return df.style.map(_color_decision, subset=["decision"])


def _turn_summary(turns: list[Turn]) -> str:
    """Build a short "N turns (M AI)" summary string for display."""
    ai_count = sum(1 for turn in turns if turn["speaker"] == "assistant")
    return f"{len(turns)} turns ({ai_count} AI)"


def _render_transcript_preview(turns: list[Turn]) -> None:
    """Show the formatted transcript inside a collapsible expander panel."""
    # st.expander creates a click-to-open section; collapsed by default here.
    with st.expander("Transcript preview", expanded=False):
        st.text(format_transcript(turns))


def _max_turn_id(turns: list[Turn] | None, df: pd.DataFrame) -> int | None:
    """Find the highest turn number, preferring the transcript over the matrix.

    Charts use this to fix the turn axis length. Prefer the parsed transcript
    (it covers all turns); fall back to the matrix rows; ``None`` if neither.
    """
    if turns:
        return max(turn["turn_id"] for turn in turns)
    if not df.empty:
        return int(df["turn_id"].max())
    return None


def _render_provenance(cache_source: str, schema_version: str, row_count: int) -> None:
    """Show a small caption noting where the displayed data came from."""
    st.caption(provenance_line(cache_source, schema_version, row_count))


def _render_visualizations(
    rows: list[dict],
    *,
    cache_source: str,
    turns: list[Turn] | None = None,
) -> None:
    """Disclosure charts above the matrix table.

    Builds the "Session overview" set of Altair charts from the extracted rows.
    ``cache_source`` and ``turns`` are keyword-only (note the ``*`` in the
    signature) so callers must name them explicitly.
    """
    # Convert the list-of-dicts rows into a DataFrame and normalize it for
    # plotting. Bail out early if there is nothing to chart.
    df = prepare_plot_df(pd.DataFrame(rows))
    if df.empty:
        return

    schema_version = infer_schema_version(rows)
    n = len(df)
    max_turn = _max_turn_id(turns, df)
    # Fall back to a generic label when no cache file backs this matrix.
    cache_label = cache_source or "in-memory matrix"

    section_heading("Session overview")
    desc(
        "Counts and patterns for inspection. These charts document what the matrix "
        "contains; they do not score researcher or AI performance. "
        "The table below is the authoritative audit trail."
    )

    section_label("Session timeline")
    _render_provenance(cache_label, schema_version, n)
    # st.altair_chart renders an Altair (Vega-Lite) chart; style_chart applies
    # the app's shared theme. use_container_width makes it span the layout width.
    st.altair_chart(style_chart(chart_session_timeline(df, max_turn=max_turn)), use_container_width=True)
    st.caption(
        "Point color = decision. Shape = record grounding level (high / medium / low)."
    )

    section_label("Analytic-stage strip")
    _render_provenance(cache_label, schema_version, n)
    st.altair_chart(style_chart(chart_analytic_stage_strip(df, max_turn=max_turn)), use_container_width=True)
    st.caption("Band color = analytic stage assigned to that turn range (same turn axis as above).")

    section_label("Decision counts and record grounding")
    _render_provenance(cache_label, schema_version, n)
    # Two side-by-side charts: decision counts on the left, grounding on the right.
    comp_left, comp_right = st.columns(2)
    with comp_left:
        st.altair_chart(style_chart(chart_decision_counts(df)), use_container_width=True)
    with comp_right:
        # The grounding chart needs newer-schema columns. If this matrix has
        # them, plot it directly; otherwise fall back to a reference cache below.
        if {"decision_stated", "reasoning_stated"}.issubset(df.columns):
            st.altair_chart(style_chart(chart_grounding_by_confidence(df)), use_container_width=True)
        else:
            grounding_rows, grounding_label = load_grounding_reference_cache()
            # Only show the separate reference grounding chart for the known
            # "long" demos — detected by these substrings in the source name.
            synthetic_long = any(
                token in cache_label
                for token in (
                    "synthetic_long",
                    "synthetic_chat_long",
                    "tracequal_example_long",
                )
            )
            if synthetic_long and grounding_rows and grounding_label:
                grounding_df = prepare_plot_df(pd.DataFrame(grounding_rows))
                st.caption(
                    "Displayed matrix uses model-reported confidence (schema v1.0.0). "
                    "Grounding composition below is drawn from a separate v1.1.0-schema "
                    "reference cache only; not merged with the displayed matrix."
                )
                _render_provenance(
                    grounding_label,
                    infer_schema_version(grounding_rows),
                    len(grounding_df),
                )
                st.altair_chart(
                    style_chart(chart_grounding_by_confidence(grounding_df)),
                    use_container_width=True,
                )
            else:
                st.info(
                    "Record-grounding composition (decision_stated / reasoning_stated) "
                    "requires schema v1.1.0 rows. The displayed cache has model-reported "
                    "confidence only. Re-run extraction with the current schema, or load "
                    "`outputs/synthetic_long_decisions__prompt-1.2.0.json` for the "
                    "committed synthetic_long reference."
                )

    section_label("Stage × decision heatmap")
    _render_provenance(cache_label, schema_version, n)
    st.altair_chart(style_chart(chart_stage_decision_heatmap(df)), use_container_width=True)

    section_label("Reviewer triage")
    _render_provenance(cache_label, schema_version, n)
    # triage_rows returns only the rows a human should double-check (low
    # confidence or unclear decision) before trusting/exporting the matrix.
    flagged = triage_rows(df)
    if flagged.empty:
        st.write("No rows with `confidence = low` or `decision = unclear`.")
    else:
        st.caption(f"{len(flagged)} row(s) flagged for hand-check before export.")
        # st.dataframe shows an interactive table. column_config renames and
        # sizes columns; st.column_config.* builds those per-column specs.
        st.dataframe(
            flagged,
            use_container_width=True,
            hide_index=True,  # don't show pandas' integer row index
            column_config={
                "turn_id": st.column_config.NumberColumn("Turn", width="small"),
                "decision": st.column_config.TextColumn("Decision", width="small"),
                "analytic_stage": st.column_config.TextColumn("Stage", width="small"),
                "confidence": st.column_config.TextColumn("Grounding level", width="small"),
                "ai_suggestion_summary": st.column_config.TextColumn(
                    "AI suggestion", width="large"
                ),
            },
        )

    st.divider()


def _render_matrix(rows: list[dict], turns: list[Turn] | None = None) -> None:
    """Render the full results view: charts, summary metrics, table, row detail."""
    # Prefer the cache filename for provenance; fall back to the source label,
    # then to a generic string. .get avoids KeyError if the key is absent.
    cache_source = st.session_state.get("cache_source") or st.session_state.get(
        "source_label", "in-memory matrix"
    )
    _render_visualizations(rows, cache_source=cache_source, turns=turns)
    section_heading("Decision matrix")

    df = pd.DataFrame(rows)
    # Four metric "cards" across the top summarizing the matrix. Which metrics
    # are shown depends on whether this schema has the *_stated columns.
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Rows", len(df))
    if not df.empty and "decision_stated" in df.columns:
        col2.metric("Decisions stated", int(df["decision_stated"].sum()))
        col3.metric("High grounding", int((df["confidence"] == "high").sum()))
        col4.metric("Low grounding", int((df["confidence"] == "low").sum()))
    elif not df.empty:
        col2.metric("High grounding", int((df["confidence"] == "high").sum()))
        col3.metric("Medium grounding", int((df["confidence"] == "medium").sum()))
        col4.metric("Low grounding", int((df["confidence"] == "low").sum()))

    # Interactive filters. multiselect lets the user pick which values to keep;
    # default= pre-selects everything so nothing is hidden until they narrow it.
    with st.expander("Filter rows", expanded=True):
        f1, f2, f3 = st.columns(3)
        decisions = f1.multiselect(
            "Decision",
            sorted(df["decision"].unique()) if not df.empty else [],
            default=sorted(df["decision"].unique()) if not df.empty else [],
        )
        stages = f2.multiselect(
            "Analytic stage",
            sorted(df["analytic_stage"].unique()) if not df.empty else [],
            default=sorted(df["analytic_stage"].unique()) if not df.empty else [],
        )
        confidences = f3.multiselect(
            "Confidence",
            ["high", "medium", "low"],
            default=["high", "medium", "low"],
        )

    # Apply each active filter. .isin keeps only rows whose value is in the
    # selected list; an empty selection means "don't filter on this field".
    filtered = df.copy()
    if decisions:
        filtered = filtered[filtered["decision"].isin(decisions)]
    if stages:
        filtered = filtered[filtered["analytic_stage"].isin(stages)]
    if confidences:
        filtered = filtered[filtered["confidence"].isin(confidences)]

    # Columns to show, in order; intersect with what actually exists so the app
    # works across schema versions that may lack some columns.
    display_cols = [
        "turn_id",
        "decision",
        "analytic_stage",
        "confidence",
        "researcher_prompt_summary",
        "ai_suggestion_summary",
        "reasoning",
    ]
    display_cols = [col for col in display_cols if col in filtered.columns]
    table = filtered[display_cols].copy()

    st.dataframe(
        _style_matrix(table),
        use_container_width=True,
        hide_index=True,
        column_config={
            "turn_id": st.column_config.NumberColumn("Turn", width="small"),
            "decision": st.column_config.TextColumn("Decision", width="small"),
            "analytic_stage": st.column_config.TextColumn("Stage", width="small"),
            "confidence": st.column_config.TextColumn("Confidence", width="small"),
            "researcher_prompt_summary": st.column_config.TextColumn(
                "Researcher prompt", width="medium"
            ),
            "ai_suggestion_summary": st.column_config.TextColumn(
                "AI suggestion", width="medium"
            ),
            "reasoning": st.column_config.TextColumn("Reasoning", width="large"),
        },
    )

    st.subheader("Row detail")
    if filtered.empty:
        st.info("No rows match the current filters.")
        return

    # Build a dropdown label per row, then let the user pick one to inspect.
    # itertuples yields each row as a namedtuple (access via row.column_name).
    labels = [
        f"Turn {row.turn_id} — {row.decision} ({row.analytic_stage})"
        for row in filtered.itertuples()
    ]
    choice = st.selectbox("Select a row", labels)
    # Map the chosen label back to its position, then fetch that row by index.
    index = labels.index(choice)
    row = filtered.iloc[index]
    st.markdown(
        f"**Turn {row['turn_id']}** · `{row['decision']}` · "
        f"`{row['analytic_stage']}` · `{row['confidence']}`"
    )
    st.markdown("**Researcher prompt**")
    st.write(row["researcher_prompt_summary"])
    st.markdown("**AI suggestion**")
    st.write(row["ai_suggestion_summary"])
    st.markdown("**Reasoning**")
    st.write(row["reasoning"])
    # Optional boolean flags indicating what was explicitly stated in the
    # transcript. .get returns None (falsy) if the column doesn't exist.
    flags = []
    if row.get("decision_stated"):
        flags.append("decision stated")
    if row.get("reasoning_stated"):
        flags.append("reasoning stated")
    if flags:
        st.caption("Transcript flags: " + ", ".join(flags))


# ---------------------------------------------------------------------------
# Page body. Everything below runs top-to-bottom on every Streamlit rerun and
# actually builds the page (the functions above are only definitions).
# ---------------------------------------------------------------------------

# Load environment variables from a project-root .env file (e.g. the API key).
load_dotenv(PROJECT_ROOT / ".env")
_init_state()  # ensure session_state keys exist before we read them

# A small styled link back to the "Kiosk exhibit" home page ("/" = the main app).
st.markdown('<div class="app-page-link">', unsafe_allow_html=True)
st.link_button("Kiosk exhibit → offline showcase", "/")
st.markdown("</div>", unsafe_allow_html=True)

page_intro(
    eyebrow="TraceQual · Interactive Studio",
    title="Upload & explore",
    lead=(
        "Upload or paste a researcher–AI coding session transcript, run extraction, "
        "and explore the decision matrix."
    ),
)

# "with st.sidebar:" places everything inside it in the left sidebar panel,
# which holds the page's settings and example/cache loader buttons.
with st.sidebar:
    st.markdown(
        '<p class="app-eyebrow" style="margin-top:0;">Settings</p>',
        unsafe_allow_html=True,
    )
    # Password-style input pre-filled from the env var if present, so the user
    # need not re-type a key already configured in .env.
    api_key = st.text_input(
        "Anthropic API key",
        value=os.getenv("ANTHROPIC_API_KEY", ""),
        type="password",
        help="Required for live extraction. Set ANTHROPIC_API_KEY in .env to skip this field.",
    )
    model = st.text_input("Model", value=os.getenv("TRACEQUAL_MODEL", DEFAULT_MODEL))
    # When checked, extraction reuses a saved result instead of re-calling the LLM.
    use_cache = st.checkbox("Use local cache when available", value=True)
    st.divider()
    st.markdown("**Versions**")
    st.text(f"Prompt {get_prompt_version()}")
    st.text(f"Schema {get_schema_version_from_prompt()} / {get_schema_version()}")
    st.divider()
    st.markdown("**Load examples**")
    # One button per built-in example; clicking loads it and reruns the page.
    for label, path in EXAMPLES.items():
        if st.button(label, use_container_width=True, key=f"sidebar_{path.name}"):
            _load_transcript(path, path.name)
            st.rerun()
    # Buttons to load committed pre-extracted matrices (only if the file exists).
    # Note Python short-circuits "and", so st.button is only drawn when the file
    # is present. Each loads matrix rows from JSON, re-parses the matching
    # transcript for context, records provenance, and reruns.
    if CACHED_SYNTHETIC_LONG.exists() and st.button(
        "Synthetic long — v1.0.0 cache (notebook fixture)",
        use_container_width=True,
        key="sidebar_synthetic_cache",
    ):
        # Load the saved decision rows from the cache JSON file.
        with CACHED_SYNTHETIC_LONG.open(encoding="utf-8") as handle:
            st.session_state.rows = json.load(handle)
        turns, source = _parse_path(SYNTHETIC_FIXTURE)
        st.session_state.turns = turns
        st.session_state.source_label = f"{source} + cached matrix"
        st.session_state.cache_source = str(CACHED_SYNTHETIC_LONG.relative_to(PROJECT_ROOT))
        st.session_state.parse_error = None
        st.session_state.extract_error = None
        st.rerun()
    if CACHED_LONG.exists() and st.button(
        "Long demo — cached extraction",
        use_container_width=True,
        key="sidebar_long_cache",
    ):
        with CACHED_LONG.open(encoding="utf-8") as handle:
            st.session_state.rows = json.load(handle)
        turns, source = _parse_path(EXAMPLES["Long demo (31 turns)"])
        st.session_state.turns = turns
        st.session_state.source_label = f"{source} + cached matrix"
        st.session_state.cache_source = str(CACHED_LONG.relative_to(PROJECT_ROOT))
        st.session_state.parse_error = None
        st.session_state.extract_error = None
        st.rerun()

# st.tabs creates labeled tab panels; the three "with tab_*:" blocks below fill
# them. They offer three ways to bring in data: upload, paste, or load a matrix.
tab_upload, tab_paste, tab_json = st.tabs(["Upload file", "Paste transcript", "Load matrix JSON"])

with tab_upload:
    _render_simulated_upload_buttons()
    section_label("Upload your own file")
    # st.file_uploader gives a file-picker widget; type= restricts extensions.
    uploaded = st.file_uploader(
        "Transcript file",
        type=["json", "md", "txt"],
        help="Claude JSON export or TraceQual Turn N (R): / Turn N (AI): text.",
    )
    # Only act once a file is chosen and the (primary-styled) button is clicked.
    if uploaded is not None and st.button("Parse upload", type="primary"):
        try:
            turns, name = _parse_upload(uploaded)
            st.session_state.turns = turns
            st.session_state.rows = None
            st.session_state.source_label = name
            st.session_state.cache_source = ""
            st.session_state.parse_error = None
            st.session_state.extract_error = None
        # Broadly catch any parse failure and surface it in the UI instead of
        # crashing the page (the noqa silences the "too broad except" linter).
        except Exception as exc:  # noqa: BLE001 — show parse errors in UI
            st.session_state.parse_error = str(exc)
            st.session_state.turns = None

with tab_paste:
    # Multi-line text box for pasting a transcript directly.
    pasted = st.text_area(
        "Paste transcript",
        height=220,
        placeholder="Turn 1 (R): ...\nTurn 2 (AI): ...",
    )
    paste_format = st.radio(
        "Format",
        ["Auto-detect", "TraceQual text", "JSON export"],
        horizontal=True,
    )
    if st.button("Parse pasted text", type="primary"):
        try:
            # Translate the radio choice into the parser's format argument.
            # None means "let the parser auto-detect the format".
            fmt = None
            if paste_format == "TraceQual text":
                fmt = "text"
            elif paste_format == "JSON export":
                fmt = "json"
            turns = parse_chat_content(pasted, format=fmt)
            st.session_state.turns = turns
            st.session_state.rows = None
            st.session_state.source_label = "pasted transcript"
            st.session_state.cache_source = ""
            st.session_state.parse_error = None
            st.session_state.extract_error = None
        except Exception as exc:  # noqa: BLE001
            st.session_state.parse_error = str(exc)
            st.session_state.turns = None

with tab_json:
    # Lets users re-open an already-extracted matrix, skipping the LLM step.
    matrix_upload = st.file_uploader(
        "Previously extracted matrix (.json)",
        type=["json"],
        key="matrix_upload",
    )
    if matrix_upload is not None and st.button("Load matrix", type="primary"):
        payload = json.loads(matrix_upload.getvalue().decode("utf-8"))
        # A valid matrix file is a JSON array (list) of row objects.
        if not isinstance(payload, list):
            st.error("Matrix file must be a JSON array of decision rows.")
        else:
            st.session_state.rows = payload
            st.session_state.source_label = matrix_upload.name
            st.session_state.cache_source = matrix_upload.name
            st.session_state.extract_error = None

# Show any stored parse error (set in the tab handlers above).
if st.session_state.parse_error:
    st.error(st.session_state.parse_error)

# Pull the current transcript and matrix out of session state into locals.
turns: list[Turn] | None = st.session_state.turns
rows: list[dict] | None = st.session_state.rows

# Once a transcript is parsed, offer extraction and (if results exist) download.
if turns:
    st.success(f"Parsed **{st.session_state.source_label}** — {_turn_summary(turns)}")
    _render_transcript_preview(turns)

    # Two equal-width columns ([1, 1] = relative widths) for the action buttons.
    extract_col, download_col = st.columns([1, 1])
    with extract_col:
        extract_clicked = st.button("Extract decision matrix", type="primary")
    with download_col:
        if rows:
            # Offers the current matrix as a downloadable JSON file.
            st.download_button(
                "Download matrix JSON",
                data=json.dumps(rows, indent=2, ensure_ascii=False),
                file_name="tracequal_decisions.json",
                mime="application/json",
                use_container_width=True,
            )

    if extract_clicked:
        # Extraction needs an API key; guard against an empty/whitespace one.
        if not api_key.strip():
            st.session_state.extract_error = (
                "Anthropic API key required. Add it in the sidebar or set "
                "ANTHROPIC_API_KEY in .env."
            )
        else:
            # st.spinner shows a "loading" indicator while the block runs.
            with st.spinner("Calling extraction model…"):
                try:
                    # Build a per-transcript, per-prompt-version cache filename so
                    # repeat runs of the same input can be reused, not re-paid for.
                    cache_path = (
                        PROJECT_ROOT
                        / "outputs"
                        / f"ui_cache__{Path(st.session_state.source_label).stem}__prompt-{get_prompt_version()}.json"
                    )
                    st.session_state.rows = extract_decisions(
                        turns,
                        api_key=api_key.strip(),
                        model=model.strip() or DEFAULT_MODEL,
                        cache_path=cache_path,
                        use_cache=use_cache,
                    )
                    st.session_state.cache_source = str(cache_path.relative_to(PROJECT_ROOT))
                    st.session_state.extract_error = None
                # Known extraction problems get their own message; anything
                # else is caught broadly so the page survives and reports it.
                except ExtractionError as exc:
                    st.session_state.extract_error = str(exc)
                except Exception as exc:  # noqa: BLE001
                    st.session_state.extract_error = f"Extraction failed: {exc}"

    if st.session_state.extract_error:
        st.error(st.session_state.extract_error)

# Final routing: show the results view if we have rows, else a guiding message.
if rows:
    # If rows exist without turns, the user loaded a matrix JSON directly.
    if not turns:
        st.info(f"Showing matrix from **{st.session_state.source_label}**.")
    _render_matrix(rows, turns=turns)
elif turns:
    st.info("Transcript parsed. Click **Extract decision matrix** to run extraction.")
else:
    st.info(
        "Simulate an upload above, choose a real file, paste a session, "
        "or open a saved matrix JSON to get started."
    )
