# TraceQual Schema Changelog

## 1.1.0 (2026-05-27)

- Added required boolean fields to decision rows:
  - `decision_stated`
  - `reasoning_stated`
- Kept `confidence` as a required enum field, but confidence is now derived in Python from the two booleans instead of self-reported by the extraction model.
- Updated schema descriptions to reflect the inspectable derivation workflow.
- Synced schema semantics with `docs/schema_notes.md` after prior drift between notes and implementation.
