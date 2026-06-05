"""Shared Streamlit theme for TraceQual kiosk and interactive studio."""

from __future__ import annotations

import html

import streamlit as st

APP_CSS = """

<style>
:root {
    --ink: #0f1419;
    --ink-soft: #141a20;
    --surface: #171d24;
    --surface-hover: #1c2430;
    --border: #2a3340;
    --border-strong: #3d4654;
    --text-primary: #f5f0e6;
    --text-body: #ece6dc;
    --text-meta: #8a8278;
    --amber: #e7b24c;
    --amber-hover: #f0c56a;
    --amber-dim: rgba(231, 178, 76, 0.15);
    --radius-sm: 6px;
    --radius-md: 10px;
    --space-xs: 0.35rem;
    --space-sm: 0.65rem;
    --space-md: 1rem;
    --space-lg: 1.5rem;
    --space-xl: 2.25rem;
    --font-serif: Georgia, 'Palatino Linotype', 'Book Antiqua', serif;
    --font-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;
    --font-mono: ui-monospace, 'SFMono-Regular', Menlo, Consolas, monospace;
    --prose-width: 42rem;
    --content-width: 1180px;
}
#MainMenu, footer, header[data-testid="stHeader"], .stDeployButton,
[data-testid="stToolbar"], [data-testid="stStatusWidget"] {
    visibility: hidden !important;
    height: 0 !important;
    display: none !important;
}
section[data-testid="stSidebar"] {
    background-color: var(--ink-soft);
    border-right: 1px solid var(--border);
}
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a,
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] span {
    color: var(--text-body) !important;
}
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[aria-current="page"] {
    background: var(--amber-dim) !important;
    color: var(--amber) !important;
}
[data-testid="stNavigation"] {
    background: var(--ink-soft) !important;
    border-bottom: 1px solid var(--border);
    margin-bottom: var(--space-md);
}
[data-testid="stNavigation"] a,
[data-testid="stNavigation"] span {
    color: var(--text-body) !important;
}
[data-testid="stNavigation"] a[aria-current="page"] {
    color: var(--amber) !important;
}
[data-testid="stLinkButton"] a {
    border: 1px solid var(--amber) !important;
    color: var(--amber) !important;
    background: transparent !important;
    font-weight: 600;
}
[data-testid="stLinkButton"] a:hover {
    background: var(--amber-dim) !important;
    color: var(--amber-hover) !important;
}
.stApp {
    background-color: var(--ink);
    color: var(--text-primary);
    font-family: var(--font-sans);
}
.block-container {
    padding-top: var(--space-md);
    padding-bottom: var(--space-xl);
    max-width: var(--content-width);
}
.block-container p,
.block-container li {
    font-size: 1.05rem;
    line-height: 1.65;
    color: var(--text-body);
}
h1, h2, h3, .kiosk-title {
    font-family: var(--font-serif);
    color: var(--text-primary);
    letter-spacing: 0.01em;
    font-weight: 600;
}
h1 { font-size: clamp(2rem, 4vw, 2.75rem); line-height: 1.15; margin-bottom: var(--space-md); }
h2 {
    font-size: clamp(1.55rem, 3vw, 2rem);
    line-height: 1.2;
    margin-top: 0;
    margin-bottom: var(--space-sm);
}
h3 {
    font-size: 1.35rem;
    line-height: 1.25;
    margin-top: var(--space-xl);
    margin-bottom: var(--space-xs);
}
.kiosk-lead {
    font-size: 1.25rem;
    line-height: 1.65;
    color: var(--text-body);
    margin-bottom: var(--space-md);
    max-width: var(--prose-width);
}
.kiosk-muted {
    color: var(--text-body);
    font-size: 1.1rem;
    line-height: 1.65;
    margin-bottom: var(--space-lg);
    max-width: var(--prose-width);
}
.kiosk-accent { color: var(--amber); }
.kiosk-header-rule {
    border: none;
    border-top: 1px solid var(--border);
    margin: var(--space-md) 0 var(--space-lg) 0;
}
.kiosk-section-heading {
    font-family: var(--font-serif);
    font-size: 1.35rem;
    font-weight: 600;
    color: var(--text-primary);
    margin: var(--space-xl) 0 var(--space-sm) 0;
    line-height: 1.3;
    padding-bottom: var(--space-xs);
    border-bottom: 1px solid var(--border);
    max-width: var(--prose-width);
}
.kiosk-section-label {
    font-family: var(--font-serif);
    font-size: 1.15rem;
    font-weight: 600;
    color: var(--text-primary);
    margin: var(--space-xl) 0 var(--space-sm) 0;
    line-height: 1.35;
    padding-left: 0.75rem;
    border-left: 3px solid var(--amber);
}
.kiosk-mono {
    font-family: var(--font-mono);
    font-size: 0.92rem;
    line-height: 1.5;
}
.kiosk-desc {
    color: var(--text-body);
    font-size: 1rem;
    line-height: 1.65;
    margin: 0 0 var(--space-md) 0;
    max-width: var(--prose-width);
}
.kiosk-chart-label {
    font-size: 1rem;
    line-height: 1.35;
    color: var(--text-primary);
    margin: 0 0 var(--space-xs) 0;
}
.kiosk-chart-label strong {
    font-weight: 700;
}
[data-testid="stCaptionContainer"] {
    margin-top: 0;
    margin-bottom: var(--space-sm);
    opacity: 1 !important;
}
[data-testid="stCaptionContainer"] p,
[data-testid="stCaptionContainer"] small,
.stCaption,
.stCaption p {
    color: #8b939d !important;
    opacity: 1 !important;
    font-size: 0.72rem !important;
    line-height: 1.45 !important;
    font-family: var(--font-mono) !important;
    letter-spacing: 0.01em;
}
div[data-testid="stExpander"] {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    margin-top: var(--space-sm);
}
div[data-testid="stExpander"] summary {
    font-weight: 600;
    color: var(--text-primary);
}
div[data-testid="stExpander"] .streamlit-expanderContent p,
div[data-testid="stExpander"] .streamlit-expanderContent li {
    font-size: 1rem !important;
    line-height: 1.65 !important;
    color: var(--text-body) !important;
}
[data-testid="stPopoverBody"] p,
[data-testid="stPopoverBody"] li {
    font-size: 1rem !important;
    line-height: 1.65 !important;
    color: var(--text-body) !important;
}
.stButton > button {
    font-family: var(--font-sans);
    font-size: 1.05rem;
    padding: 0.6rem 1.25rem;
    border-radius: var(--radius-sm);
    border: 1px solid var(--amber);
    background: var(--amber);
    color: var(--ink);
    font-weight: 600;
    transition: background 0.15s ease, border-color 0.15s ease, transform 0.1s ease;
}
.stButton > button:hover {
    background: var(--amber-hover);
    border-color: var(--amber-hover);
    color: var(--ink);
}
.stButton > button:focus-visible {
    outline: 2px solid var(--amber-hover);
    outline-offset: 2px;
}
button[kind="secondary"] {
    background: transparent !important;
    color: var(--amber) !important;
    border: 1px solid var(--amber) !important;
}
button[kind="secondary"]:hover {
    background: var(--amber-dim) !important;
}
div[data-testid="column"]:has(.kiosk-session-title) {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: var(--space-lg) var(--space-lg) var(--space-md);
    min-height: 13rem;
    transition: border-color 0.2s ease, background 0.2s ease;
}
div[data-testid="column"]:has(.kiosk-session-title):hover {
    border-color: var(--amber);
    background: var(--surface-hover);
}
div[data-testid="column"]:has(.kiosk-session-title) .stButton > button {
    width: 100%;
    min-height: 2.85rem;
    margin-top: var(--space-xs);
}
.kiosk-session-title {
    font-family: var(--font-serif);
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--text-primary);
    line-height: 1.35;
    margin: 0 0 var(--space-sm) 0;
}
.kiosk-session-desc {
    font-size: 1rem;
    line-height: 1.6;
    color: var(--text-body);
    margin: 0 0 var(--space-md) 0;
}
.kiosk-row-panel {
    background: var(--surface);
    border-left: 4px solid var(--amber);
    padding: var(--space-md) var(--space-lg);
    border-radius: var(--radius-sm);
    margin: var(--space-md) 0 var(--space-lg) 0;
    max-width: var(--prose-width);
}
.kiosk-row-panel p {
    font-size: 1rem;
    line-height: 1.65;
    color: var(--text-body);
    margin: 0 0 var(--space-sm) 0;
}
.kiosk-row-panel p:last-child { margin-bottom: 0; }
.kiosk-row-panel p strong { color: var(--text-primary); }
.kiosk-row-panel .kiosk-row-meta {
    font-size: 0.92rem;
    margin-bottom: var(--space-sm);
}
.kiosk-row-panel .kiosk-muted {
    font-size: 0.95rem;
    margin-bottom: 0;
    max-width: none;
}
.kiosk-timeline-hint {
    border: 1px solid var(--amber);
    background: var(--amber-dim);
    color: var(--text-primary);
    padding: var(--space-md) var(--space-lg);
    border-radius: var(--radius-sm);
    margin: 0 0 var(--space-md) 0;
    font-size: 1.05rem;
    line-height: 1.6;
    max-width: var(--prose-width);
}
.kiosk-timeline-hint strong { color: var(--amber); }
hr.kiosk-footer-rule {
    margin-top: var(--space-xl);
    margin-bottom: var(--space-lg);
    border: none;
    border-top: 1px solid var(--border);
}
.kiosk-footer-meta {
    font-size: 0.95rem;
    line-height: 1.6;
    color: var(--text-body);
    margin-bottom: var(--space-xs);
}
.kiosk-footer-link {
    font-family: var(--font-mono);
    font-size: 0.82rem;
    color: var(--text-meta);
}
[data-testid="stMetricLabel"] {
    color: var(--text-meta) !important;
    font-size: 0.9rem !important;
}
[data-testid="stMetricValue"] {
    color: var(--text-primary) !important;
    font-size: 1.25rem !important;
}
.kiosk-closing-section {
    margin-top: var(--space-xl);
    padding-top: var(--space-lg);
    border-top: 1px solid var(--border);
}
.kiosk-closing-section h3 {
    font-size: 1.35rem;
    color: var(--text-primary);
    margin-bottom: var(--space-sm);
    max-width: var(--prose-width);
}
.kiosk-closing-intro {
    color: var(--text-body);
    font-size: 1.05rem;
    line-height: 1.65;
    margin-bottom: var(--space-md);
    max-width: var(--prose-width);
}
.kiosk-closing-panel {
    background: var(--ink-soft);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: var(--space-md) var(--space-lg);
    font-size: 1rem;
    line-height: 1.65;
    color: var(--text-body);
    max-width: var(--prose-width);
}
.kiosk-closing-panel-open {
    border-style: dashed;
    border-color: var(--border-strong);
}
.kiosk-closing-body {
    color: var(--text-body);
    font-size: 1rem;
    line-height: 1.65;
    margin: var(--space-sm) 0 0 0;
}
.kiosk-closing-card-anchor {
    border-left: 3px solid var(--amber);
    margin-top: var(--space-md);
    padding: var(--space-xs) 0 var(--space-xs) var(--space-md);
    font-size: 0.98rem;
    color: var(--text-body);
    line-height: 1.6;
}
.kiosk-closing-close {
    color: var(--text-body);
    font-size: 1rem;
    font-style: italic;
    line-height: 1.6;
    margin: var(--space-md) 0 0 0;
    opacity: 0.92;
}
.kiosk-nav-caption {
    text-align: center;
    color: var(--text-meta);
    font-size: 0.95rem;
    line-height: 1.5;
    margin: var(--space-sm) 0 0 0;
}
[data-testid="stAlert"] p {
    font-size: 1rem !important;
    line-height: 1.6 !important;
}
[data-testid="stMetric"] {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: var(--space-sm) var(--space-md);
}
hr {
    margin: var(--space-xl) 0 var(--space-lg) 0;
    border: none;
    border-top: 1px solid var(--border);
}

.app-eyebrow {
    font-family: var(--font-mono);
    font-size: 0.88rem;
    color: var(--amber);
    letter-spacing: 0.06em;
    text-transform: uppercase;
    margin: 0 0 var(--space-sm) 0;
}
.app-page-link {
    margin: 0 0 var(--space-lg) 0;
}
div[data-testid="column"]:has(.app-demo-label) {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: var(--space-md) var(--space-md) var(--space-sm);
    min-height: 10rem;
}
div[data-testid="column"]:has(.app-demo-label) .stButton > button {
    width: 100%;
    margin-top: var(--space-xs);
}
.app-demo-label {
    font-family: var(--font-serif);
    font-size: 1.05rem;
    font-weight: 600;
    color: var(--text-primary);
    line-height: 1.35;
    margin: 0 0 var(--space-xs) 0;
}
.app-demo-detail {
    font-size: 0.88rem;
    line-height: 1.5;
    color: var(--text-meta);
    margin: 0 0 var(--space-sm) 0;
}
div[data-testid="stTabs"] [data-baseweb="tab-list"] {
    gap: var(--space-sm);
    border-bottom: 1px solid var(--border);
}
div[data-testid="stTabs"] button[role="tab"] {
    background: transparent !important;
    color: var(--text-meta) !important;
    font-weight: 600;
}
div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
    color: var(--amber) !important;
    border-bottom: 2px solid var(--amber) !important;
}
[data-testid="stFileUploader"] {
    background: var(--surface);
    border: 1px dashed var(--border-strong);
    border-radius: var(--radius-md);
    padding: var(--space-md);
}
[data-testid="stFileUploader"] label,
[data-testid="stFileUploader"] small {
    color: var(--text-body) !important;
}
.stTextInput input,
.stTextArea textarea {
    background-color: var(--surface) !important;
    color: var(--text-body) !important;
    border-color: var(--border) !important;
}
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {
    font-family: var(--font-serif);
    color: var(--text-primary) !important;
}
section[data-testid="stSidebar"] .stMarkdown p,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] .stText {
    color: var(--text-body) !important;
}
[data-testid="stDataFrame"] {
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
}
div[data-testid="stAlert"] {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    color: var(--text-body) !important;
}
.stSuccess {
    background: var(--amber-dim) !important;
    border: 1px solid var(--border-strong) !important;
}
</style>
"""


def inject_app_css() -> None:
    """Inject the shared TraceQual app stylesheet."""
    st.markdown(APP_CSS, unsafe_allow_html=True)


def style_chart(chart):
    """Altair theme matching the ink / amber app shell."""
    return (
        chart.configure(background="transparent")
        .configure_title(color="#f5f0e6", fontSize=15, font="Georgia")
        .configure_axis(labelColor="#8a8278", titleColor="#ece6dc", labelFontSize=12)
        .configure_legend(labelColor="#ece6dc", titleColor="#ece6dc", labelFontSize=12)
    )


def section_label(text: str) -> None:
    st.markdown(
        f'<p class="kiosk-section-label">{html.escape(text)}</p>',
        unsafe_allow_html=True,
    )


def section_heading(text: str) -> None:
    st.markdown(
        f'<p class="kiosk-section-heading">{html.escape(text)}</p>',
        unsafe_allow_html=True,
    )


def desc(text: str) -> None:
    st.markdown(f'<p class="kiosk-desc">{html.escape(text)}</p>', unsafe_allow_html=True)


def page_intro(*, eyebrow: str, title: str, lead: str) -> None:
    st.markdown(
        f'<p class="app-eyebrow">{html.escape(eyebrow)}</p>'
        f'<h1 class="kiosk-title">{html.escape(title)}</h1>'
        f'<p class="kiosk-lead">{html.escape(lead)}</p>',
        unsafe_allow_html=True,
    )
