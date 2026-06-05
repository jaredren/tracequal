# TraceQual synthetic examples

Three ready-to-extract transcripts. All content is synthetic, with no real
participant data, so they are safe to commit and to show at a demo. All three
were verified to parse with `tracequal/parser.py`.

## Files

| File | Format | Parses to | Use |
|---|---|---|---|
| `tracequal_example_long.md` | text fixture (`Turn N (R):`) | 31 turns, 15 AI | Full-coverage run: exercises every part of the schema |
| `tracequal_example_short.md` | text fixture | 11 turns, 5 AI | Quick live demo |
| `tracequal_example_short.json` | Claude `chat_messages` export | 11 turns, 5 AI | Same conversation as the short md, for demoing the JSON path and the `timestamp` column |

Supported input is by file extension: `.json` (Claude export or OpenAI-style
`messages`), and `.md` / `.txt` (the `Turn N (R):` fixture format). ChatGPT
tree exports are not supported in v1; use the paste/markdown path.

## What the long example is built to exercise

- All five `decision` values: accepted, modified, rejected, deferred, unclear.
- All six `analytic_stage` phases, including a coding-to-theming transition.
- The skip rules: a factual self-correction (turn 8), an administrative
  exchange (turn 14), and a meta-reflection turn (turn 28).
- One AI turn with two distinct suggestions (turn 6), which should split into
  two rows.
- A spread of confidence: rows where the researcher states both decision and
  reasoning (high), states only the decision (medium), and where the decision
  is left implicit (low).

### Intended reading of the long example (sanity-check target)

This is how a careful coder would expect the matrix to come out. Use it to
check the extractor against intent.

| AI turn | Suggestion | Decision | Stage | Confidence |
|---|---|---|---|---|
| 2 | adopt sensitizing concepts | rejected | familiarization | high |
| 4 | code calendar_blocking | accepted | coding | medium |
| 6 | code notification_triage | accepted | coding | medium |
| 6 | code device_separation | modified (renamed device_boundaries) | coding | high |
| 8 | miscount correction | skip | n/a | n/a |
| 10 | attention-as-labor theme | deferred | coding | high |
| 12 | code household_negotiation | unclear | coding | low |
| 14 | export CSV | skip | n/a | n/a |
| 16 | memo paraphrase | modified (tighten) | writeup | high |
| 18 | merge two codes | rejected | reviewing | high |
| 20 | theme: defending attention | accepted | theming | medium |
| 22 | second candidate theme | modified (renamed) | theming | high |
| 24 | merge two themes | rejected | reviewing | high |
| 26 | theme definition | accepted | defining | medium |
| 28 | meta reflection | skip | n/a | n/a |
| 30 | exemplar quote | accepted | writeup | medium |

About thirteen rows, no row for the three skipped turns.

Demo point: the extractor may diverge from this reading. v1 has a documented
inclusion bias (it tends to emit rows for turns that should be skipped) and
temperature-0 non-determinism (two runs can differ by a row). A gap between
this intended reading and the actual output is not a failure to hide; it is
exactly the behavior the methods reflection documents.

## How to run

Live extraction calls the Anthropic API, so it needs `ANTHROPIC_API_KEY` in
`.env`. From a Python session in the repo root:

    from tracequal.parser import parse_chat
    from tracequal.extractor import extract_decisions, default_cache_path

    turns = parse_chat("tracequal_example_long.md")
    rows = extract_decisions(turns, cache_path=default_cache_path(), use_cache=True)

Set `use_cache=True` with a `cache_path` to avoid re-billing the API on reruns.
The committed-cache path the notebook uses needs no key; that only applies to
extractions already cached in `outputs/`.
