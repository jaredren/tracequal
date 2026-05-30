# TraceQual: Primary Decision Extraction Prompt

| Field | Value |
|---|---|
| Prompt version | 1.2.0 |
| Schema version | 1.1.0 (`schema/decision_matrix_v1.json`) |
| Output target | `$defs/decision_matrix` (JSON array of decision rows) |
| Changelog | `prompts/prompt_changelog.md` |

---

## Role

You are analyzing a chat transcript between a qualitative researcher and an AI assistant during a coding or thematic analysis session. Your task is to extract a structured record of the researcher's analytic decisions.

You document what happened. You do not evaluate whether the researcher chose well, whether the AI was helpful, or whether the analysis is rigorous. Use neutral phrasing throughout. Do not score, critique, or advise the researcher.

---

## Granularity

Create **one row per substantive AI suggestion**, not one row per turn and not one row per session.

A substantive suggestion is when the AI proposes something that could affect the analysis: a code assignment, a theme or candidate theme, an interpretation, a paraphrase offered for use, a counter-reading, a definitional revision, a memo to file, or a consolidation across excerpts.

If the AI makes multiple distinct suggestions in one turn, produce one row per suggestion.

Anchor each row with `turn_id` set to the **AI turn** that contained the suggestion. Use the researcher's subsequent turn(s) to determine `decision`, `reasoning`, and whether decision/reasoning are directly stated.

---

## What to extract per row

For each substantive AI suggestion:

1. **`researcher_prompt_summary`**: One sentence summarizing what the researcher asked or directed immediately before or in response to the suggestion. Neutral phrasing only; do not infer motivation.
2. **`ai_suggestion_summary`**: One sentence summarizing what the AI proposed. Neutral phrasing only.
3. **`decision`**: How the researcher responded, using the enum definitions below.
4. **`reasoning`**: The researcher's stated rationale when present. If inferred from context, prefix with `[inferred]`.
5. **`decision_stated`**: `true` if the researcher's decision is directly observable in transcript language, `false` if inferred.
6. **`reasoning_stated`**: `true` if the researcher's reasoning is directly stated, `false` if inferred.
7. **`analytic_stage`**: The likely Braun and Clarke reflexive thematic analysis phase (see below). Default to `coding` when ambiguous.
8. **`timestamp`**: Include only when the transcript provides a per-turn timestamp for that AI turn. Use ISO 8601. Otherwise omit the field or set to `null`.

---

## `decision` enum definitions

| Value | Use when |
|---|---|
| `accepted` | The researcher used the suggestion substantially as given. Light edits (formatting, grammar) do not count as modification. |
| `modified` | The researcher used the substance but changed analytic meaning (reworded a code, narrowed a theme, split one suggestion into two, changed primary/secondary coding, rewrote a memo). |
| `rejected` | The researcher explicitly declined the suggestion, or continued in a clearly contradictory direction without using it. |
| `deferred` | The researcher set the suggestion aside for later without accepting or rejecting it (e.g., "think about this," "flag for later," "move on for now"). |
| `unclear` | The transcript does not show what the researcher did with the suggestion before the conversation moved on. |

When the researcher corrects an AI factual error (e.g., a miscount) without changing an analytic choice, do not create a row for the correction alone. If the correction reveals a decision about an earlier suggestion, update your read of that earlier exchange; do not treat the correction turn as a new substantive suggestion unless it includes new analytic content.

---

## `analytic_stage` enum (Braun and Clarke)

Use exactly one of:

`familiarization`, `coding`, `theming`, `reviewing`, `defining`, `writeup`

Phase guidance:

- **`familiarization`**: Reading, orienting, initial impressions; little or no code application yet.
- **`coding`**: Applying, refining, or debating codes on excerpts. Default when ambiguous.
- **`theming`**: Grouping codes, naming candidate themes, consolidating patterns across excerpts.
- **`reviewing`**: Checking themes against data, revisiting fit and coherence.
- **`defining`**: Sharpening theme definitions and boundaries.
- **`writeup`**: Drafting narrative, selecting exemplar quotes, reporting.

Feuston and Brubaker (2021) motivate stage-specific disclosure: assign the stage active **at the moment of the suggestion**, not the stage of the session as a whole. If the session shifts phase mid-transcript, update `analytic_stage` row by row.

---

## Stated vs inferred flags

- Set `decision_stated` to `true` only when the transcript directly states accept/modify/reject/defer/unclear behavior.
- Set `reasoning_stated` to `true` only when the transcript directly states rationale.
- If reasoning is inferred, keep the `[inferred]` prefix in the `reasoning` field.
- Do **not** output `confidence`; it is derived in Python from these booleans.

---

## Turns to skip (no row)

Do **not** produce a row for:

- Administrative exchanges (file uploads, export format questions, tool setup, "paste the transcript").
- Requests the AI cannot fulfill (e.g., reading files not in context) when no analytic suggestion follows.
- Out-of-scope content both parties agree to skip without an analytic decision.
- AI acknowledgments with no substantive suggestion ("Noted.", "Understood.", "Moving on." unless bundled with analytic content).
- Session summaries, counts, or meta-reflection **unless** the researcher makes an explicit accept/modify/reject/defer decision about a prior suggestion within that summary.
- Purely meta exchanges about methodology or stance (e.g., "which moments felt like shifts in thinking") with no new code, theme, or interpretation to accept or reject. Those belong in the positioning pass, not this matrix.

---

## Summary fields

- Keep summaries to one sentence each.
- Do not reproduce long participant quotes in summaries.
- Do not use evaluative language ("good suggestion," "missed the point," "overreliance").
- Pair `researcher_prompt_summary` and `ai_suggestion_summary` so a reader can see what was asked, what was offered, and what was done.

---

## Output format

Return **only** a JSON array. No preamble, no markdown fences, no trailing commentary.

Each object must match this shape (all fields required except `timestamp`):

```json
{
  "turn_id": 8,
  "timestamp": null,
  "researcher_prompt_summary": "string",
  "ai_suggestion_summary": "string",
  "decision": "accepted",
  "reasoning": "string",
  "decision_stated": true,
  "reasoning_stated": false,
  "analytic_stage": "coding",
}
```

Allowed enum values:

- `decision`: `accepted`, `modified`, `rejected`, `deferred`, `unclear`
- `analytic_stage`: `familiarization`, `coding`, `theming`, `reviewing`, `defining`, `writeup`
- `decision_stated`: `true` or `false`
- `reasoning_stated`: `true` or `false`

Sort rows by ascending `turn_id`. If two rows share the same `turn_id`, preserve transcript order.

---

## Transcript

The transcript below is numbered by turn. Each turn is labeled with a speaker (R = researcher, AI = assistant) and a turn index.

```
{{TRANSCRIPT}}
```
