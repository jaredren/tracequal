"""TraceQual kiosk exhibit — offline, unattended showcase demo."""

from __future__ import annotations

import html
import json
import time
import importlib
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import tracequal.viz as _viz
importlib.reload(_viz)

from tracequal.parser import Turn, parse_chat
from tracequal.ui_theme import desc as _kiosk_desc
from tracequal.ui_theme import inject_app_css
from tracequal.ui_theme import section_heading as _section_heading
from tracequal.ui_theme import section_label as _section_label
from tracequal.ui_theme import style_chart as _style_kiosk_chart

DECISION_COLORS = _viz.DECISION_COLORS
chart_analytic_stage_strip = _viz.chart_analytic_stage_strip
chart_decision_counts = _viz.chart_decision_counts
chart_grounding_by_confidence = _viz.chart_grounding_by_confidence
chart_session_timeline = _viz.chart_session_timeline
chart_stage_decision_heatmap = _viz.chart_stage_decision_heatmap
infer_schema_version = _viz.infer_schema_version
prepare_plot_df = _viz.prepare_plot_df
triage_rows = _viz.triage_rows

PROJECT_ROOT = Path(__file__).resolve().parent
DOCS = PROJECT_ROOT / "docs"
OUTPUTS = PROJECT_ROOT / "outputs"
ASSETS = PROJECT_ROOT / "assets"
QR_PATH = ASSETS / "kiosk_qr.png"

IDLE_SECONDS = 90

# Which closing theme each kiosk case shows (reassign session ids here).
CLOSING_SECTION_BY_SESSION: dict[str, str] = {
    "synthetic_main": "justify_later",
    "focus_time": "disclose_writeup",
    "grounding_detail": "train_ai_question",
}

KIOSK_SESSIONS: list[dict[str, Any]] = [
    {
        "id": "synthetic_main",
        "title": "Coding interview excerpts with AI",
        "subtitle": (
            "A researcher works through a long synthetic coding session. "
            "TraceQual documents 23 decisions about AI suggestions."
        ),
        "fixture": DOCS / "synthetic_chat_long.md",
        "cache": OUTPUTS / "synthetic_long_decisions__prompt-1.0.0.json",
        "grounding_cache": OUTPUTS / "synthetic_long_decisions__prompt-1.2.0.json",
    },
    {
        "id": "focus_time",
        "title": "Remote workers protecting focus time",
        "subtitle": (
            "A shorter, approachable session about coding themes on distraction "
            "and calendar habits. 12 documented decisions."
        ),
        "fixture": DOCS / "tracequal_example_long.md",
        "cache": OUTPUTS / "tracequal_example_long__prompt-1.0.0.json",
        "grounding_cache": None,
    },
    {
        "id": "grounding_detail",
        "title": "Stated vs inferred record grounding",
        "subtitle": (
            "The same long synthetic session with schema v1.1.0: each row shows "
            "whether the decision and reasoning were stated in the transcript or inferred."
        ),
        "fixture": DOCS / "synthetic_chat_long.md",
        "cache": OUTPUTS / "synthetic_long_decisions__prompt-1.2.0.json",
        "grounding_cache": None,
    },
]


INTERACTIVE_STUDIO_URL = "/Interactive_Studio"


def _chart_label(text: str) -> None:
    st.markdown(
        f'<p class="kiosk-chart-label"><strong>{html.escape(text)}</strong></p>',
        unsafe_allow_html=True,
    )


def _render_kiosk_chart(chart) -> None:
    st.altair_chart(_style_kiosk_chart(chart), use_container_width=True)


def _scroll_to_top() -> None:
    components.html(
        """
        <script>
            (function () {
                const doc = window.parent.document;
                const anchorId = "tracequal-case-top";

                function scrollAll() {
                    const anchor = doc.getElementById(anchorId);
                    const selectors = [
                        "section.main",
                        '[data-testid="stAppViewContainer"]',
                        '[data-testid="stMainBlockContainer"]',
                        '[data-testid="stVerticalBlock"]',
                        ".main .block-container",
                    ];
                    selectors.forEach((selector) => {
                        doc.querySelectorAll(selector).forEach((el) => {
                            el.scrollTop = 0;
                            if (el.scrollTo) {
                                el.scrollTo({ top: 0, left: 0, behavior: "auto" });
                            }
                        });
                    });
                    if (anchor) {
                        anchor.scrollIntoView({ block: "start", inline: "nearest" });
                    }
                    doc.documentElement.scrollTop = 0;
                    doc.body.scrollTop = 0;
                    try {
                        window.parent.scrollTo(0, 0);
                    } catch (_) {}
                }

                scrollAll();
                [0, 50, 150, 350, 700, 1200].forEach((delay) => {
                    setTimeout(scrollAll, delay);
                });
            })();
        </script>
        """,
        height=0,
    )


def _init_state() -> None:
    defaults = {
        "page": "landing",
        "session_id": None,
        "selected_row_index": None,
        "last_activity": time.time(),
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _touch() -> None:
    st.session_state.last_activity = time.time()


def _reset_kiosk() -> None:
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    _init_state()


@st.fragment(run_every=timedelta(seconds=10))
def _idle_reset_watcher() -> None:
    if st.session_state.get("page") == "landing":
        return
    idle_for = time.time() - st.session_state.get("last_activity", time.time())
    if idle_for >= IDLE_SECONDS:
        _reset_kiosk()
        st.rerun()


def _style_matrix(df: pd.DataFrame):
    def _color_decision(value: str) -> str:
        color = DECISION_COLORS.get(value, "")
        return f"background-color: {color}; color: #0f1419" if color else ""

    return df.style.map(_color_decision, subset=["decision"])


def _load_session(session_id: str) -> tuple[list[dict], list[Turn], dict[str, Any]]:
    config = next(item for item in KIOSK_SESSIONS if item["id"] == session_id)
    with config["cache"].open(encoding="utf-8") as handle:
        rows = json.load(handle)
    turns = parse_chat(config["fixture"])
    return rows, turns, config


def _max_turn_id(turns: list[Turn], df: pd.DataFrame) -> int:
    return max(max(turn["turn_id"] for turn in turns), int(df["turn_id"].max()))


def _decision_plain(decision: str) -> str:
    labels = {
        "accepted": "The researcher accepted the AI suggestion.",
        "modified": "The researcher changed the AI suggestion before using it.",
        "rejected": "The researcher did not use the AI suggestion.",
        "deferred": "The researcher set the suggestion aside for later.",
        "unclear": "The transcript does not clearly show what the researcher did next.",
    }
    return labels.get(decision, decision)


def _pick_anchor_row(rows: list[dict]) -> dict | None:
    """Prefer rejected or modified rows for the live example; fall back to any row."""
    if not rows:
        return None
    for preferred in ("rejected", "modified"):
        for row in rows:
            if row.get("decision") == preferred:
                return row
    return rows[0]


def _decision_counts(rows: list[dict]) -> dict[str, int]:
    counts = {key: 0 for key in ("accepted", "modified", "rejected", "deferred", "unclear")}
    for row in rows:
        decision = row.get("decision")
        if decision in counts:
            counts[decision] += 1
    return counts


def _has_grounding_fields(rows: list[dict]) -> bool:
    return bool(rows) and (
        "reasoning_stated" in rows[0] or "decision_stated" in rows[0]
    )


def _count_reasoning_stated(rows: list[dict]) -> int:
    return sum(1 for row in rows if row.get("reasoning_stated") is True)


def _render_closing_panel(
    *,
    heading: str,
    intro: str,
    anchor_html: str = "",
    body_html: str = "",
    close: str,
    open_question: bool = False,
) -> None:
    panel_class = "kiosk-closing-panel kiosk-closing-panel-open" if open_question else "kiosk-closing-panel"
    st.markdown('<div class="kiosk-closing-section">', unsafe_allow_html=True)
    st.markdown(f"### {html.escape(heading)}")
    if open_question:
        _kiosk_desc("Open question — not a product claim.")
    st.markdown(f'<p class="kiosk-closing-intro">{html.escape(intro)}</p>', unsafe_allow_html=True)
    parts = [f'<div class="{panel_class}">']
    if body_html:
        parts.append(f'<p class="kiosk-closing-body">{body_html}</p>')
    if anchor_html:
        parts.append(f'<div class="kiosk-closing-card-anchor">{anchor_html}</div>')
    parts.append(f'<p class="kiosk-closing-close">{html.escape(close)}</p>')
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def _render_closing_justify_later(rows: list[dict]) -> None:
    anchor = _pick_anchor_row(rows)
    anchor_html = ""
    if anchor is not None:
        decision = html.escape(str(anchor["decision"]))
        suggestion = html.escape(str(anchor["ai_suggestion_summary"]))
        reasoning = html.escape(str(anchor["reasoning"]))
        anchor_html = (
            f"Here the researcher <strong>{decision}</strong> the suggestion to {suggestion}. "
            f'Recorded reason: &ldquo;{reasoning}&rdquo; Months later, that line answers '
            f'&ldquo;why did we do it that way?&rdquo; with no one reconstructing it from memory.'
        )
    _render_closing_panel(
        heading="Justify a decision later",
        intro=(
            "Coding choices get questioned long after they are made: in a team meeting, a reviewer "
            "comment, or a replication attempt. The recorded row is the receipt."
        ),
        anchor_html=anchor_html,
        close="Disclosure turns a private judgment into something a collaborator can check.",
    )


def _render_closing_disclose_writeup(rows: list[dict]) -> None:
    counts = _decision_counts(rows)
    n = len(rows)
    anchor_html = (
        f"In this session, <strong>{n}</strong> AI suggestions were logged: "
        f"<strong>{counts['accepted']}</strong> accepted, "
        f"<strong>{counts['modified']}</strong> modified, "
        f"<strong>{counts['rejected']}</strong> rejected, "
        f"the rest deferred or unclear. A reader can see exactly where the AI shaped the work "
        f"and weigh the analysis with that in view."
    )
    _render_closing_panel(
        heading="Disclose AI involvement in the writeup",
        intro=(
            "Venues and reviewers increasingly want to know where AI touched an analysis. "
            "This record can travel straight into a methods appendix."
        ),
        anchor_html=anchor_html,
        close="The point is not to hide the AI or to defend it, only to make its role legible.",
    )


def _render_closing_train_ai_question(rows: list[dict]) -> None:
    n = len(rows)
    anchor_html = ""
    if _has_grounding_fields(rows):
        stated = _count_reasoning_stated(rows)
        anchor_html = (
            f"And the signal is thinner than it looks: only <strong>{stated}</strong> of "
            f"<strong>{n}</strong> rows had the reasoning explicitly stated; the rest were inferred."
        )
    _render_closing_panel(
        heading="Could these records teach an AI to code? (open question)",
        intro=(
            "Compiled across many sessions, these rows record how one researcher decides: "
            "what they accept, change, and refuse, and sometimes why."
        ),
        body_html=(
            "That could in principle train an AI coder on a researcher's own conventions. "
            "It is also where TraceQual's stance gets tested: the tool exists to document AI "
            "involvement, not to automate coding, and a model trained on one person's habits "
            "could quietly steer the next analysis toward them."
        ),
        anchor_html=anchor_html,
        close="The audited record makes this question askable. It does not answer it.",
        open_question=True,
    )


def _render_case_closing(session_id: str, rows: list[dict]) -> None:
    theme = CLOSING_SECTION_BY_SESSION.get(session_id, "justify_later")
    if theme == "justify_later":
        _render_closing_justify_later(rows)
    elif theme == "disclose_writeup":
        _render_closing_disclose_writeup(rows)
    elif theme == "train_ai_question":
        _render_closing_train_ai_question(rows)
    else:
        _render_closing_justify_later(rows)


def _next_session_id(current_id: str) -> str:
    session_ids = [session["id"] for session in KIOSK_SESSIONS]
    index = session_ids.index(current_id)
    return session_ids[(index + 1) % len(session_ids)]


def _render_case_navigation(session_id: str) -> None:
    next_id = _next_session_id(session_id)
    next_title = next(session["title"] for session in KIOSK_SESSIONS if session["id"] == next_id)

    st.markdown("---")
    back_col, next_col = st.columns(2, gap="medium")
    with back_col:
        if st.button("← Go back", key="go_back_bottom", type="secondary", use_container_width=True):
            _touch()
            st.session_state.page = "picker"
            st.session_state.session_id = None
            st.session_state.selected_row_index = None
            st.rerun()
    with next_col:
        if st.button("Next case →", key="next_case_bottom", type="primary", use_container_width=True):
            _touch()
            st.session_state.page = "explore"
            st.session_state.session_id = next_id
            st.session_state.selected_row_index = None
            st.session_state.scroll_to_top = True
            st.rerun()
    st.markdown(
        f'<p class="kiosk-nav-caption">Next: {html.escape(next_title)}</p>',
        unsafe_allow_html=True,
    )


def _render_header() -> None:
    left, mid, _ = st.columns([2, 3, 2])
    with left:
        if st.button("← Start over", key="start_over"):
            _touch()
            _reset_kiosk()
            st.rerun()
    with mid:
        st.markdown(
            '<p class="kiosk-mono kiosk-accent" style="text-align:center;margin:0;">'
            "TraceQual · disclosure scaffold</p>",
            unsafe_allow_html=True,
        )
    st.markdown('<hr class="kiosk-header-rule">', unsafe_allow_html=True)


def _render_demo_switch() -> None:
    st.link_button(
        "Interactive Studio → upload, paste, extract",
        INTERACTIVE_STUDIO_URL,
    )


def _render_landing() -> None:
    _render_demo_switch()
    st.markdown(
        '<h1 class="kiosk-title">When AI helps with qualitative coding,<br>'
        '<span class="kiosk-accent">what did the researcher decide?</span></h1>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p class="kiosk-lead">TraceQual turns a researcher–AI chat into a structured '
        "<strong>decision matrix</strong>: a readable record of every time the researcher "
        "accepted, changed, rejected, or deferred an <strong>AI suggestion</strong> during "
        "<strong>qualitative coding</strong> (labeling and interpreting interview or field text).</p>",
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p class="kiosk-muted">Researchers already note in their papers that they used AI, but usually as '
        "a single line that hides which choices it touched. TraceQual makes that record granular and "
        "low-effort: it turns the coding conversation itself into an inspectable, "
        "<strong>per-decision trail</strong>. It documents involvement; it does not automate coding or "
        "judge the researcher.</p>",
        unsafe_allow_html=True,
    )
    if st.button("Explore a sample session →", type="primary", use_container_width=False):
        _touch()
        st.session_state.page = "picker"
        st.rerun()

    with st.expander("How it works"):
        st.markdown(
            "1. A researcher and AI chat while coding qualitative data.\n\n"
            "2. TraceQual reads the transcript and emits one row per substantive AI suggestion.\n\n"
            "3. Each row records the suggestion, the researcher's response, the analytic stage, "
            "and how much was **stated in the transcript** vs **inferred** by the tool."
        )
    with st.expander("What we learned from building it"):
        st.markdown(
            "- **Prompt changes are not always improvements.** A targeted revision can fix one "
            "failure and break others.\n"
            "- **Temperature-zero runs can still differ.** Two extractions at the same settings "
            "may produce different row counts.\n"
            "- **Record-grounding labels often cluster in the middle** when researchers state "
            "decisions but not reasons — a pattern in how people talk to AI, not a bug to hide."
        )


def _render_session_picker() -> None:
    _render_header()
    st.markdown("## Choose a sample session")
    st.markdown(
        '<p class="kiosk-muted">All samples are preloaded from committed research artifacts. '
        "No typing, uploads, or network required.</p>",
        unsafe_allow_html=True,
    )
    cols = st.columns(len(KIOSK_SESSIONS), gap="large")
    for column, session in zip(cols, KIOSK_SESSIONS, strict=True):
        with column:
            st.markdown(
                f'<p class="kiosk-session-title">{html.escape(session["title"])}</p>'
                f'<p class="kiosk-session-desc">{html.escape(session["subtitle"])}</p>',
                unsafe_allow_html=True,
            )
            if st.button("Open session →", key=f"pick_{session['id']}", use_container_width=True):
                _touch()
                st.session_state.page = "explore"
                st.session_state.session_id = session["id"]
                st.session_state.selected_row_index = None
                st.rerun()


def render_provenance(cache_file: str, schema: str, n: int) -> None:
    """Small muted source line above charts."""
    line = f"Source: {cache_file} · Schema v{schema} · n={n} rows"
    st.caption(line)


def _render_row_story(row: dict) -> None:
    st.markdown(
        f'<div class="kiosk-row-panel">'
        f'<p class="kiosk-mono kiosk-accent kiosk-row-meta">Turn {row["turn_id"]} · '
        f'{html.escape(str(row["decision"]))} · {html.escape(str(row["analytic_stage"]))}</p>'
        f"<p><strong>AI suggested:</strong> {html.escape(str(row['ai_suggestion_summary']))}</p>"
        f"<p><strong>Researcher decided:</strong> {html.escape(_decision_plain(row['decision']))}</p>"
        f"<p><strong>Why (from transcript or inference):</strong> {html.escape(str(row['reasoning']))}</p>"
        f'<p class="kiosk-muted">Record grounding level: <span class="kiosk-mono">'
        f'{html.escape(str(row["confidence"]))}</span> — how much of this row is directly stated in the chat.</p>'
        f"</div>",
        unsafe_allow_html=True,
    )


def _render_explore() -> None:
    _render_header()
    session_id = st.session_state.session_id
    if not session_id:
        st.session_state.page = "picker"
        st.rerun()
        return

    st.markdown('<div id="tracequal-case-top"></div>', unsafe_allow_html=True)

    rows, turns, config = _load_session(session_id)
    df = prepare_plot_df(pd.DataFrame(rows))
    cache_label = str(config["cache"].relative_to(PROJECT_ROOT))
    schema_version = infer_schema_version(rows)
    n = len(df)
    max_turn = _max_turn_id(turns, df)

    st.markdown(f"## {config['title']}")
    st.markdown(
        f'<p class="kiosk-muted">{html.escape(config["subtitle"])}</p>',
        unsafe_allow_html=True,
    )

    _section_heading("Session views")
    _kiosk_desc(
        "Each view counts rows (n), not rates. Colors match the decision matrix below. "
        "Charts document what was recorded; they do not evaluate the researcher or the AI."
    )

    _section_label("Timeline")
    render_provenance(cache_label, schema_version, n)
    if st.session_state.selected_row_index is None:
        st.markdown(
            '<div class="kiosk-timeline-hint">'
            "<strong>Try it:</strong> click any <strong>amber-outlined dot</strong> below "
            "to read that decision — what the AI suggested, what the researcher decided, and why."
            "</div>",
            unsafe_allow_html=True,
        )
    else:
        _kiosk_desc(
            "Each dot is one matrix row. Color = decision. Shape = record grounding level. "
            "Click another dot to explore a different decision."
        )
    timeline = _style_kiosk_chart(
        chart_session_timeline(df, max_turn=max_turn, selectable=True)
    )
    event = st.altair_chart(
        timeline,
        use_container_width=True,
        on_select="rerun",
        key="timeline_select",
    )
    if event and event.selection and event.selection.get("timeline_select"):
        points = event.selection["timeline_select"]
        if points:
            st.session_state.selected_row_index = int(points[0].get("row_index", 0))
            _touch()

    if st.session_state.selected_row_index is not None:
        idx = st.session_state.selected_row_index
        if 0 <= idx < len(rows):
            _render_row_story(rows[idx])

    _section_label("Analytic-stage strip")
    _kiosk_desc(
        "How to read: colored bands show which phase of analysis the session was in "
        "along the same turn axis (familiarization → coding → theming → …)."
    )
    render_provenance(cache_label, schema_version, n)
    _render_kiosk_chart(chart_analytic_stage_strip(df, max_turn=max_turn))

    _section_label("Decision counts and record grounding")
    has_inline_grounding = {"decision_stated", "reasoning_stated"}.issubset(df.columns)
    grounding_cache_path = config.get("grounding_cache")
    has_grounding_reference = (
        not has_inline_grounding
        and grounding_cache_path is not None
        and grounding_cache_path.exists()
    )
    how_to_read = (
        "How to read: left = row counts by decision (n). "
        "Right = record grounding level (high / medium / low) stacked by transcript evidence "
        "(Both stated · Reasoning inferred · Decision inferred)."
    )
    if has_grounding_reference:
        how_to_read += (
            " The right chart uses a separate v1.1.0-schema reference cache for the same "
            "transcript (not merged into the decision matrix below)."
        )
    _kiosk_desc(how_to_read)
    render_provenance(cache_label, schema_version, n)

    grounding_plot_df: pd.DataFrame | None = None
    if has_inline_grounding:
        grounding_plot_df = df
    elif has_grounding_reference:
        with grounding_cache_path.open(encoding="utf-8") as handle:
            grounding_rows = json.load(handle)
        grounding_plot_df = prepare_plot_df(pd.DataFrame(grounding_rows))
        reference_label = str(grounding_cache_path.relative_to(PROJECT_ROOT))
        render_provenance(
            reference_label,
            infer_schema_version(grounding_rows),
            len(grounding_plot_df),
        )

    left, right = st.columns(2)
    with left:
        _chart_label("Decision counts")
        _render_kiosk_chart(chart_decision_counts(df))
    with right:
        if grounding_plot_df is not None:
            _chart_label("Record grounding by transcript evidence")
            _render_kiosk_chart(chart_grounding_by_confidence(grounding_plot_df))
        else:
            st.info(
                "Record-grounding composition requires schema v1.1.0 rows with "
                "decision_stated / reasoning_stated fields."
            )

    _section_label("Stage × decision heatmap")
    _kiosk_desc("How to read: cell counts (n) show where decisions cluster by analytic stage.")
    render_provenance(cache_label, schema_version, n)
    st.altair_chart(
        _style_kiosk_chart(chart_stage_decision_heatmap(df)),
        use_container_width=True,
    )

    _section_label("Reviewer triage")
    _kiosk_desc(
        "How to read: rows with low record grounding or unclear decisions — "
        "hand-check these before citing the matrix."
    )
    render_provenance(cache_label, schema_version, n)
    flagged = triage_rows(df)
    if flagged.empty:
        st.write("No rows flagged for triage in this sample.")
    else:
        st.dataframe(
            flagged,
            use_container_width=True,
            hide_index=True,
            column_config={
                "turn_id": st.column_config.NumberColumn("Turn"),
                "decision": st.column_config.TextColumn("Decision"),
                "analytic_stage": st.column_config.TextColumn("Stage"),
                "confidence": st.column_config.TextColumn("Grounding level"),
                "ai_suggestion_summary": st.column_config.TextColumn("AI suggestion"),
            },
        )

    st.markdown("---")
    _section_heading("Decision matrix")
    _kiosk_desc("Primary audit trail. Full text stays here — not summarized in the charts above.")

    display_cols = [
        "turn_id",
        "decision",
        "analytic_stage",
        "confidence",
        "researcher_prompt_summary",
        "ai_suggestion_summary",
        "reasoning",
    ]
    table = df[[col for col in display_cols if col in df.columns]].copy()
    st.dataframe(
        _style_matrix(table),
        use_container_width=True,
        hide_index=True,
        column_config={
            "turn_id": st.column_config.NumberColumn("Turn", width="small"),
            "decision": st.column_config.TextColumn("Decision", width="small"),
            "analytic_stage": st.column_config.TextColumn("Stage", width="small"),
            "confidence": st.column_config.TextColumn("Grounding level", width="small"),
            "researcher_prompt_summary": st.column_config.TextColumn(
                "Researcher prompt", width="medium"
            ),
            "ai_suggestion_summary": st.column_config.TextColumn(
                "AI suggestion", width="medium"
            ),
            "reasoning": st.column_config.TextColumn("Reasoning", width="large"),
        },
    )

    _render_case_closing(session_id, rows)
    _render_case_navigation(session_id)

    if st.session_state.pop("scroll_to_top", False):
        _scroll_to_top()


def _render_footer() -> None:
    st.markdown('<hr class="kiosk-footer-rule">', unsafe_allow_html=True)
    footer_left, footer_right = st.columns([3, 1], gap="large")
    with footer_left:
        st.markdown(
            '<p class="kiosk-footer-meta"><strong>TraceQual</strong> · HCDE 530 · Jared Ren · '
            "A disclosure scaffold for AI-assisted qualitative analysis. "
            "This kiosk runs offline from committed sample data.</p>",
            unsafe_allow_html=True,
        )
        st.markdown(
            '<span class="kiosk-footer-link">'
            "nbviewer.org/github/jaredren/tracequal/…/mp2_notebook.ipynb</span>",
            unsafe_allow_html=True,
        )
    with footer_right:
        if QR_PATH.exists():
            st.image(str(QR_PATH), caption="Full notebook", width=120)


def _validate_sessions() -> list[str]:
    """Return error messages for missing kiosk artifacts."""
    errors: list[str] = []
    for session in KIOSK_SESSIONS:
        if not session["fixture"].exists():
            errors.append(f"Missing fixture: {session['fixture']}")
        if not session["cache"].exists():
            errors.append(f"Missing cache: {session['cache']}")
        grounding = session.get("grounding_cache")
        if grounding is not None and not grounding.exists():
            errors.append(f"Missing grounding cache: {grounding}")
    if not QR_PATH.exists():
        errors.append(f"Missing QR asset: {QR_PATH}")
    return errors


def run_kiosk() -> None:
    _init_state()
    _touch()
    _idle_reset_watcher()

    missing = _validate_sessions()
    if missing:
        st.error("Kiosk assets missing:\n" + "\n".join(f"- {item}" for item in missing))
        return

    page = st.session_state.page
    if page == "landing":
        _render_landing()
    elif page == "picker":
        _render_session_picker()
    elif page == "explore":
        _render_explore()
    else:
        _reset_kiosk()
        st.rerun()

    _render_footer()


def run() -> None:
    st.set_page_config(
        page_title="TraceQual",
        page_icon="📋",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_app_css()
    pg = st.navigation(
        [
            st.Page(run_kiosk, title="Kiosk exhibit", icon="📋", default=True),
            st.Page(
                "pages/1_Interactive_Studio.py",
                title="Interactive Studio",
                icon="🧪",
                url_path="Interactive_Studio",
            ),
        ],
        position="top",
    )
    pg.run()


if __name__ == "__main__":
    run()
