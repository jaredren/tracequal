"""TraceQual interactive studio — upload or paste a transcript, extract, explore."""

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

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCS = PROJECT_ROOT / "docs"
EXAMPLES = {
    "Short demo (11 turns)": DOCS / "tracequal_example_short.md",
    "Long demo (31 turns)": DOCS / "tracequal_example_long.md",
    "Short demo (Claude JSON)": DOCS / "tracequal_example_short.json",
}
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
CACHED_LONG = PROJECT_ROOT / "outputs" / "tracequal_example_long__prompt-1.0.0.json"
CACHED_SYNTHETIC_LONG = PROJECT_ROOT / "outputs" / "synthetic_long_decisions__prompt-1.0.0.json"
SYNTHETIC_FIXTURE = DOCS / "synthetic_chat_long.md"


def _init_state() -> None:
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
    suffix = Path(uploaded.name).suffix.lower()
    text = uploaded.getvalue().decode("utf-8")
    if suffix == ".json":
        turns = parse_chat_content(text, format="json")
    elif suffix in {".md", ".txt"}:
        turns = parse_chat_content(text, format="text")
    else:
        raise ValueError("Unsupported file type. Upload .json, .md, or .txt.")
    return turns, uploaded.name


def _parse_path(path: Path) -> tuple[list[Turn], str]:
    return parse_chat(path), str(path.relative_to(PROJECT_ROOT))


def _load_transcript(path: Path, source_label: str) -> None:
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
    section_label("Simulate upload")
    desc(
        "Demo shortcuts — loads a sample transcript as if it were uploaded here. "
        "No file picker needed."
    )
    cols = st.columns(len(DEMO_UPLOADS))
    for column, demo in zip(cols, DEMO_UPLOADS, strict=True):
        with column:
            st.markdown(
                f'<p class="app-demo-label">{demo["label"]}</p>'
                f'<p class="app-demo-detail">{demo["detail"]}</p>',
                unsafe_allow_html=True,
            )
            if st.button(
                f"Upload {demo['filename']}",
                key=f"simulate_{demo['key']}",
                use_container_width=True,
            ):
                _simulate_upload(Path(demo["path"]), str(demo["filename"]))
                st.rerun()
    st.divider()


def _style_matrix(df: pd.DataFrame):
    def _color_decision(value: str) -> str:
        color = DECISION_COLORS.get(value, "")
        return f"background-color: {color}" if color else ""

    return df.style.map(_color_decision, subset=["decision"])


def _turn_summary(turns: list[Turn]) -> str:
    ai_count = sum(1 for turn in turns if turn["speaker"] == "assistant")
    return f"{len(turns)} turns ({ai_count} AI)"


def _render_transcript_preview(turns: list[Turn]) -> None:
    with st.expander("Transcript preview", expanded=False):
        st.text(format_transcript(turns))


def _max_turn_id(turns: list[Turn] | None, df: pd.DataFrame) -> int | None:
    if turns:
        return max(turn["turn_id"] for turn in turns)
    if not df.empty:
        return int(df["turn_id"].max())
    return None


def _render_provenance(cache_source: str, schema_version: str, row_count: int) -> None:
    st.caption(provenance_line(cache_source, schema_version, row_count))


def _render_visualizations(
    rows: list[dict],
    *,
    cache_source: str,
    turns: list[Turn] | None = None,
) -> None:
    """Disclosure charts above the matrix table."""
    df = prepare_plot_df(pd.DataFrame(rows))
    if df.empty:
        return

    schema_version = infer_schema_version(rows)
    n = len(df)
    max_turn = _max_turn_id(turns, df)
    cache_label = cache_source or "in-memory matrix"

    section_heading("Session overview")
    desc(
        "Counts and patterns for inspection. These charts document what the matrix "
        "contains; they do not score researcher or AI performance. "
        "The table below is the authoritative audit trail."
    )

    section_label("Session timeline")
    _render_provenance(cache_label, schema_version, n)
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
    comp_left, comp_right = st.columns(2)
    with comp_left:
        st.altair_chart(style_chart(chart_decision_counts(df)), use_container_width=True)
    with comp_right:
        if {"decision_stated", "reasoning_stated"}.issubset(df.columns):
            st.altair_chart(style_chart(chart_grounding_by_confidence(df)), use_container_width=True)
        else:
            grounding_rows, grounding_label = load_grounding_reference_cache()
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
    flagged = triage_rows(df)
    if flagged.empty:
        st.write("No rows with `confidence = low` or `decision = unclear`.")
    else:
        st.caption(f"{len(flagged)} row(s) flagged for hand-check before export.")
        st.dataframe(
            flagged,
            use_container_width=True,
            hide_index=True,
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
    cache_source = st.session_state.get("cache_source") or st.session_state.get(
        "source_label", "in-memory matrix"
    )
    _render_visualizations(rows, cache_source=cache_source, turns=turns)
    section_heading("Decision matrix")

    df = pd.DataFrame(rows)
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

    filtered = df.copy()
    if decisions:
        filtered = filtered[filtered["decision"].isin(decisions)]
    if stages:
        filtered = filtered[filtered["analytic_stage"].isin(stages)]
    if confidences:
        filtered = filtered[filtered["confidence"].isin(confidences)]

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

    labels = [
        f"Turn {row.turn_id} — {row.decision} ({row.analytic_stage})"
        for row in filtered.itertuples()
    ]
    choice = st.selectbox("Select a row", labels)
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
    flags = []
    if row.get("decision_stated"):
        flags.append("decision stated")
    if row.get("reasoning_stated"):
        flags.append("reasoning stated")
    if flags:
        st.caption("Transcript flags: " + ", ".join(flags))


load_dotenv(PROJECT_ROOT / ".env")
_init_state()

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

with st.sidebar:
    st.markdown(
        '<p class="app-eyebrow" style="margin-top:0;">Settings</p>',
        unsafe_allow_html=True,
    )
    api_key = st.text_input(
        "Anthropic API key",
        value=os.getenv("ANTHROPIC_API_KEY", ""),
        type="password",
        help="Required for live extraction. Set ANTHROPIC_API_KEY in .env to skip this field.",
    )
    model = st.text_input("Model", value=os.getenv("TRACEQUAL_MODEL", DEFAULT_MODEL))
    use_cache = st.checkbox("Use local cache when available", value=True)
    st.divider()
    st.markdown("**Versions**")
    st.text(f"Prompt {get_prompt_version()}")
    st.text(f"Schema {get_schema_version_from_prompt()} / {get_schema_version()}")
    st.divider()
    st.markdown("**Load examples**")
    for label, path in EXAMPLES.items():
        if st.button(label, use_container_width=True, key=f"sidebar_{path.name}"):
            _load_transcript(path, path.name)
            st.rerun()
    if CACHED_SYNTHETIC_LONG.exists() and st.button(
        "Synthetic long — v1.0.0 cache (notebook fixture)",
        use_container_width=True,
        key="sidebar_synthetic_cache",
    ):
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

tab_upload, tab_paste, tab_json = st.tabs(["Upload file", "Paste transcript", "Load matrix JSON"])

with tab_upload:
    _render_simulated_upload_buttons()
    section_label("Upload your own file")
    uploaded = st.file_uploader(
        "Transcript file",
        type=["json", "md", "txt"],
        help="Claude JSON export or TraceQual Turn N (R): / Turn N (AI): text.",
    )
    if uploaded is not None and st.button("Parse upload", type="primary"):
        try:
            turns, name = _parse_upload(uploaded)
            st.session_state.turns = turns
            st.session_state.rows = None
            st.session_state.source_label = name
            st.session_state.cache_source = ""
            st.session_state.parse_error = None
            st.session_state.extract_error = None
        except Exception as exc:  # noqa: BLE001 — show parse errors in UI
            st.session_state.parse_error = str(exc)
            st.session_state.turns = None

with tab_paste:
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
    matrix_upload = st.file_uploader(
        "Previously extracted matrix (.json)",
        type=["json"],
        key="matrix_upload",
    )
    if matrix_upload is not None and st.button("Load matrix", type="primary"):
        payload = json.loads(matrix_upload.getvalue().decode("utf-8"))
        if not isinstance(payload, list):
            st.error("Matrix file must be a JSON array of decision rows.")
        else:
            st.session_state.rows = payload
            st.session_state.source_label = matrix_upload.name
            st.session_state.cache_source = matrix_upload.name
            st.session_state.extract_error = None

if st.session_state.parse_error:
    st.error(st.session_state.parse_error)

turns: list[Turn] | None = st.session_state.turns
rows: list[dict] | None = st.session_state.rows

if turns:
    st.success(f"Parsed **{st.session_state.source_label}** — {_turn_summary(turns)}")
    _render_transcript_preview(turns)

    extract_col, download_col = st.columns([1, 1])
    with extract_col:
        extract_clicked = st.button("Extract decision matrix", type="primary")
    with download_col:
        if rows:
            st.download_button(
                "Download matrix JSON",
                data=json.dumps(rows, indent=2, ensure_ascii=False),
                file_name="tracequal_decisions.json",
                mime="application/json",
                use_container_width=True,
            )

    if extract_clicked:
        if not api_key.strip():
            st.session_state.extract_error = (
                "Anthropic API key required. Add it in the sidebar or set "
                "ANTHROPIC_API_KEY in .env."
            )
        else:
            with st.spinner("Calling extraction model…"):
                try:
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
                except ExtractionError as exc:
                    st.session_state.extract_error = str(exc)
                except Exception as exc:  # noqa: BLE001
                    st.session_state.extract_error = f"Extraction failed: {exc}"

    if st.session_state.extract_error:
        st.error(st.session_state.extract_error)

if rows:
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
