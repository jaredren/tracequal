# TraceQual Prompt Changelog

Log every revision to versioned prompts in this file. Do not edit `extract_decisions.md` or `positioning_pass.md` without an entry here.

## extract_decisions.md

### 1.0.0 (2026-05-24)

- Initial release aligned with `schema/decision_matrix_v1.json` v1.0.0.
- One row per substantive AI suggestion; `turn_id` anchors to the AI turn.
- Braun and Clarke six-phase `analytic_stage` enum; default `coding` when ambiguous.
- `[inferred]` prefix convention paired with `confidence` levels per `docs/schema_notes.md`.
- Skip rules for administrative turns, out-of-scope skips, meta-reflection, and AI error corrections.
- Output: JSON array only, no markdown fences.

### 1.0.1 (2026-05-24)

- Default extraction model set to `claude-sonnet-4-6` in tracequal/extractor.py.
- Extraction API calls use temperature=0 for reproducible validation runs.

### 1.1.0 (2026-05-25)

Motivated by harness failures on `decision_enum_accepted`, `decision_enum_rejected`, `skip_turns_24_26`, and `skip_turns_45_46` (2026-05-25 validation run, prompt v1.0.0).

- Added inclusion criterion: appendix-ready analytic decision vs. conversational scaffolding.
- Added implicit partial acceptance rule: offloaded dimensions (e.g., valence tagging) yield `modified`, not `accepted`; reasoning must name the offloaded dimension.
- Added negative examples for capability limits (turns 24-26), out-of-scope skips (turns 45-46), and factual self-corrections (turns 55-57).
- Clarified skip boundary between substantive analytic decisions and administrative or course-correcting exchanges.

### 1.0.0 (re-locked, 2026-05-25)

Reverted from 1.1.0 after harness validation showed a net regression (10 PASS at v1.1.0 versus 12 PASS at v1.0.0 on the synthetic_chat_long fixture). The v1.1.0 revisions did not address the targeted failures (skip_turns_24_26, skip_turns_45_46, decision_enum_rejected) and introduced two new failures (decision_enum_modified, low_confidence_t38). See outputs/synthetic_long_decisions__prompt-1.0.0.json and outputs/synthetic_long_decisions__prompt-1.1.0.json for the cached extractions from both runs.

### 1.2.0 (2026-05-27)

- Replaced model self-reported `confidence` with explicit evidence flags: `decision_stated` and `reasoning_stated`.
- Retained `[inferred]` prefix convention in `reasoning` while moving confidence derivation into Python.
- Updated output contract to remove prompt-side confidence assignment.
- Aligned prompt with schema v1.1.0 confidence derivation rules and calibration workflow.
