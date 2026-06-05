# TraceQual

TraceQual is infrastructure for making AI involvement in qualitative analysis legible. It reads a researcher-AI chat transcript from a coding or thematic analysis session and produces a structured decision matrix documenting each analytic choice the researcher made about an AI suggestion. The output is intended for inspection in a methods appendix or audit trail, not for automating coding. TraceQual does not use AI to code data; it documents AI involvement that is already happening.

## Live deliverable

The primary artifact is the narrative notebook. GitHub's native notebook renderer fails on this file (a known issue with some notebook outputs); use one of the links below instead.

- **Primary:** [View on nbviewer](https://nbviewer.org/github/jaredren/tracequal/blob/main/notebooks/mp2_notebook.ipynb)
- **Fallback:** [Static HTML export](notebooks/mp2_notebook.html) — if nbviewer is unavailable, open this file in a browser from the repo.

## What's in this repo

- **Notebook:** `notebooks/mp2_notebook.ipynb` renders the locked v1 extraction as a readable artifact.
- **Source code:** `tracequal/` contains parsing, extraction, schema validation, and export utilities.
- **Schema and prompt:** `schema/` and `prompts/` define the decision matrix and the versioned extraction prompt.
- **Validation harness:** `scripts/validate_extraction.py` checks extraction output against fixture expectations.
- **Locked cached extractions:** `outputs/` holds versioned JSON caches from validation runs (two files are committed for reproducibility).
- **Methods documentation:** `docs/schema_notes.md` and `docs/methods_reflection.md` document schema rationale and build findings.

## Interactive app

Two demo modes share one Streamlit process. Run:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
streamlit run app.py
```

Open the local URL and use the **sidebar** to switch pages:

| Page | Purpose |
|------|---------|
| **Kiosk exhibit** | Offline showcase for an unattended table demo. Preloaded sample caches only — no API key, uploads, or live extraction. |
| **Interactive Studio** | Original workflow: upload or paste a transcript, run extraction (API key required), explore charts and the decision matrix. Sidebar includes one-click demo loaders and cached matrices. |

For the kiosk, open in a full-screen browser window. Use **Start over** (or wait ~90 seconds idle) between visitors.

For interactive extraction, set `ANTHROPIC_API_KEY` in `.env` or paste a key in the sidebar.

Static disclosure charts for the notebook / HTML deliverable:

```bash
python scripts/export_viz.py
```

PNG files are written to `notebooks/viz/`.

## How to run it locally

```bash
git clone https://github.com/jaredren/tracequal.git
cd tracequal
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/validate_extraction.py --cache-path outputs/synthetic_long_decisions__prompt-1.0.0.json
```

The validation harness validates extraction output against the current schema (v1.1.0). The committed caches under `outputs/` (`prompt-1.0.0` and `prompt-1.1.0`) are historical artifacts from earlier schema versions; the notebook reads them directly with pandas without re-validation. That version coupling is deliberate: a cache produced under an older schema should not pass validation against a newer one, which is the correct behavior for an audit-trail tool.

## Supported input formats

- **Tested and supported:** Claude account export JSON using a flat `chat_messages` list; TraceQual markdown/paste transcript format (fixture-style turn headers).
- **Supported in principle but not yet tested on a real export:** Generic `messages` JSON shape currently recognized by the parser.
- **Known unsupported in v1:** ChatGPT account export JSON with tree-structured `mapping`. Recommendation for ChatGPT users: copy the conversation and use the paste/markdown path.

## Citation (WIP)

```bibtex
@misc{tracequal2026,
  author       = {Jared Ren},
  title        = {TraceQual: A Disclosure Scaffold for AI-Assisted Qualitative Analysis},
  year         = {[YEAR]},
  howpublished = {\url{https://github.com/jaredren/tracequal}},
  note         = {HCDE 530 MP2 artifact}
}
```
