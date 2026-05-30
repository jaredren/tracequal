# TraceQual: Project Structure for Cursor

A disclosure scaffold for solo qualitative researchers using LLMs mid-analysis. Built as a Python notebook published to GitHub.

## TL;DR

Single repo, one main notebook, supporting Python modules for parsing and prompting, a versioned schema, a fixed prompt template, and a small fixture set for testing. The notebook is the deliverable. Everything else exists to keep the notebook clean and reproducible.

---

## Directory layout

```
tracequal/
├── README.md                          # Project pitch, usage, citation
├── LICENSE                            # MIT or CC-BY-4.0
├── requirements.txt                   # Minimal: anthropic, pandas, python-dotenv
├── .env.example                       # ANTHROPIC_API_KEY=
├── .gitignore                         # .env, __pycache__, outputs/, *.local.*
│
├── notebooks/
│   └── tracequal_demo.ipynb           # Main deliverable, GitHub-rendered
│
├── tracequal/                         # Importable package
│   ├── __init__.py
│   ├── parser.py                      # Chat transcript parsing (Claude/ChatGPT exports)
│   ├── extractor.py                   # LLM-based decision extraction
│   ├── schema.py                      # Decision matrix schema + validation
│   ├── positioning.py                 # Secondary stance-shift analysis
│   └── export.py                      # CSV and Markdown writers
│
├── prompts/
│   ├── extract_decisions.md           # Primary extraction prompt, versioned
│   ├── positioning_pass.md            # Secondary epistemic positioning prompt
│   └── prompt_changelog.md            # Documents prompt revisions
│
├── schema/
│   ├── decision_matrix_v1.json        # JSON schema for the matrix
│   └── schema_notes.md                # Rationale for each column, citations
│
├── fixtures/
│   ├── synthetic_chat_short.txt       # 15-turn synthetic Claude session
│   ├── synthetic_chat_long.txt        # 60-turn session with stance shifts
│   └── README.md                      # How fixtures were generated, what they test
│
├── outputs/                           # Gitignored, runtime artifacts
│   └── .gitkeep
│
└── docs/
    ├── methods_reflection.md          # 1-page reflection on tool's affordances/limits
    └── future_work.md                 # Browser extension framing, multi-researcher mode
```

---

## What goes in the main notebook

`notebooks/tracequal_demo.ipynb` is the GitHub-facing artifact. Structure it as a narrative, not a script dump.

1. **Header and motivation** (Markdown). Two paragraphs. The problem, the contribution, the scope boundary.
2. **Schema walkthrough** (Markdown). Walk through the decision matrix columns and cite the methods literature that motivates each one. This is the intellectual core.
3. **Load a fixture** (Code). Use `fixtures/synthetic_chat_long.txt` so the notebook runs end-to-end without an API call needed to demo.
4. **Parse the transcript** (Code). Show `parser.parse_chat(path)` returning a list of turn dicts.
5. **Run extraction** (Code). Call `extractor.extract_decisions(turns, prompt_path)`. Cache results to `outputs/` so the notebook can re-render without re-spending API tokens.
6. **Display the matrix** (Code + Markdown). Render the resulting DataFrame inline. Annotate two or three rows in Markdown to show what the tool captured well.
7. **Positioning pass** (Code). Run the secondary analysis. Show the stance-shift summary.
8. **Export** (Code). Write CSV and Markdown to `outputs/`.
9. **Reflection** (Markdown). One paragraph on what the tool did not capture. Link to `docs/methods_reflection.md`.

---

## The decision matrix schema (proposed v1)

Eight columns. Each row is one AI interaction the researcher engaged with.

| Column | Type | Description |
|---|---|---|
| `turn_id` | int | Sequential turn number in the chat session |
| `timestamp` | ISO 8601 or null | Captured if the export includes it |
| `researcher_prompt_summary` | string | One-sentence summary of what the researcher asked |
| `ai_suggestion_summary` | string | One-sentence summary of what the AI proposed |
| `decision` | enum | `accepted`, `modified`, `rejected`, `deferred`, `unclear` |
| `reasoning` | string | The researcher's stated or inferred rationale |
| `analytic_stage` | enum | `familiarization`, `coding`, `theming`, `interpretation`, `writeup` (Braun and Clarke phases) |
| `confidence` | enum | `high`, `medium`, `low` — how confident the extractor is in this row |

A separate `positioning_log` table tracks epistemic stance shifts: `turn_id`, `shift_type` (e.g., `broadening`, `narrowing`, `reframing`), `evidence_quote`, `note`.

---

## The primary extraction prompt (sketch)

Save as `prompts/extract_decisions.md`. Version it. Do not edit silently; log changes to `prompt_changelog.md`.

```
You are analyzing a chat transcript between a qualitative researcher and an
AI assistant during a coding or thematic analysis session. Your task is to
extract a structured record of the researcher's analytic decisions.

For each turn where the AI made a substantive suggestion (a code, a theme,
an interpretation, a paraphrase, a counter-reading), identify:

1. What the AI suggested (one sentence, neutral phrasing).
2. What the researcher did next: accepted as-is, modified before using,
   rejected, deferred for later, or unclear from the transcript.
3. The researcher's stated reasoning, if present. If the reasoning is
   inferred rather than stated, mark confidence as "low" and note the
   inference in the reasoning field with a "[inferred]" prefix.
4. The likely analytic stage using Braun and Clarke's six phases:
   familiarization, coding, theming, reviewing, defining, writeup.
   Use "coding" if ambiguous.

Skip turns that are administrative (file uploads, clarifying questions
about format, off-topic).

Output a JSON array. Each object must match this schema:
{
  "turn_id": <int>,
  "researcher_prompt_summary": <string>,
  "ai_suggestion_summary": <string>,
  "decision": "accepted" | "modified" | "rejected" | "deferred" | "unclear",
  "reasoning": <string>,
  "analytic_stage": "familiarization" | "coding" | "theming" | "reviewing" | "defining" | "writeup",
  "confidence": "high" | "medium" | "low"
}

Return only the JSON array. No preamble, no markdown fences.
```

The positioning prompt runs after this and takes the extracted rows plus the original transcript as input, looking for moments where the researcher's framing of the data shifted.

---

## requirements.txt

```
anthropic>=0.40.0
pandas>=2.0.0
python-dotenv>=1.0.0
jsonschema>=4.20.0
```

Keep it minimal. No Streamlit, no Flask, no Jupyter widgets. The notebook is the interface for v1.

---

## README.md skeleton

1. One-paragraph pitch (the problem, what the tool produces, who it's for)
2. Quickstart (clone, install, set API key, run notebook)
3. The schema, with a small example matrix screenshot
4. Methods note: how to cite the tool, what it does not do, link to reflection
5. Roadmap: browser extension, multi-researcher mode, integration with Dedoose exports
6. Citation: BibTeX entry for the repo itself

---

## What to build first, in order

The temptation will be to start with the parser. Don't. Start with the schema, then write three or four matrix rows by hand from one of your own real Claude logs. That hand-coding tells you whether the schema is right before you build anything around it.

1. Write `schema/decision_matrix_v1.json` and `schema_notes.md`. Cite Feuston and Brubaker (2021), McDonald et al. (2019) on IRR norms, Barany et al. (2024) on hybrid coding, and Braun and Clarke for the analytic stages.
2. Hand-code one of your own chat sessions into the schema. If anything feels awkward, revise the schema before writing code.
3. Write the extraction prompt. Test it on the same chat session by pasting into Claude or running locally. Compare to your hand-coded version.
4. Write `parser.py` for one input format (Claude export JSON is the cleanest starting point).
5. Write `extractor.py` as a thin wrapper around the Anthropic SDK.
6. Build the notebook narrative.
7. Run the positioning pass.
8. Write the reflection.

---

## Scope guards

Three rules to keep this from sprawling.

First, no multi-researcher features in v1. Solo researcher, one chat session at a time. Multi-coder reconciliation is a separate paper.

Second, no live capture. The user pastes or uploads a completed transcript. Real-time logging is the browser extension future-work claim.

Third, no judgment of the researcher's decisions. The tool documents, it does not evaluate. Avoid any prompt language that scores or critiques the researcher's choices. This is a defensibility point for IRB and for reviewers who would otherwise see this as surveillance.

---

## What the GitHub repo signals to a PhD admissions reader

A clean schema document with citations, a versioned prompt with a changelog, a working notebook on a synthetic fixture, and a one-page methods reflection. That combination signals methodological seriousness more than a polished web app would. Min Kyung Lee's lab, Tawanna Dillahunt's group, and Karen Levy would all read this kind of artifact as evidence you can do reflexive, infrastructure-aware research, which is exactly the positioning you want for your application materials.
