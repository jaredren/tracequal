# MP2 Competency Claims

**Course** HCDE 530 &nbsp;|&nbsp; **Project** TraceQual: A Disclosure Scaffold for AI-Assisted Qualitative Analysis &nbsp;|&nbsp; **Platform** Cursor + Python

This file makes four competency claims. Each claim names the domain, states what I did, and points to specific files, commits, or sections of the repository where the evidence lives.

---

## C8 — Building and Deploying a Complete Tool (required)

**Claim.** TraceQual is a complete, scoped Python tool that takes a researcher-AI chat transcript as input and produces a structured decision matrix documenting every analytic decision the researcher made about an AI suggestion. It is intended for solo qualitative researchers and methods reviewers who need an inspectable audit trail of AI involvement in coding and thematic analysis. The deliverable is published as a Jupyter notebook on GitHub at `notebooks/mp2_notebook.ipynb`, which renders the locked v1.0.0 extraction, the schema rationale, and the validation harness results in a single readable artifact.

**Evidence in the repo.**

- `notebooks/mp2_notebook.ipynb`: the live deliverable. Renders the matrix from the committed cache, walks through the schema, embeds the harness output, summarizes findings.
- `tracequal/` package: the working code (parser, extractor, schema validator, positioning stub).
- `schema/decision_matrix_v1.json` and `schema/schema_changelog.md`: the versioned schema that anchors the tool's output contract.
- `scripts/validate_extraction.py`: the validation harness that reports 12 PASS, 4 FAIL, 3 PENDING on the locked v1.0.0 run.
- `outputs/synthetic_long_decisions__prompt-1.0.0.json` and `__prompt-1.1.0.json` and `__prompt-1.2.0.json`: three committed cached extractions documenting the tool's iteration history.
- `docs/methods_reflection.md`: the 2,000-word reflection on what the tool captures and what it misses.
- `README.md`: explains the tool to someone outside the course, with a live link.

**Honest account of what went wrong.** The largest single problem was a provenance bug in the harness: the function that printed the prompt version in the report header was actually reading the schema version row from the prompt file, because the regex matched the wrong row and the function name was misleading. The bug went unnoticed for two iterations, including one full re-run with `--no-cache`, before the diagnostic showed that the header version had never changed. I split the function into two honestly-named helpers (`get_prompt_version` and `get_schema_version_from_prompt`), made the cache version-aware by including the prompt version in the cache filename, and committed the unsuccessful prompt v1.1.0 alongside v1.0.0 as part of the audit trail. The episode is documented in `prompts/prompt_changelog.md` and discussed in the methods reflection's Finding 2.

**What I would scope differently next time.** I would add a `transcript_span` field to the schema from the start so decisions could be anchored back to specific passages in the participant transcript. The v1 schema can record what the researcher decided about an AI suggestion but not which part of the data the suggestion was about. This gap is described as future work in `docs/future_work.md`.

---

## C2 — Code Literacy and Documentation

**Claim.** The tool is documented at every level a future reader needs to verify the work. The schema and the extraction prompt are independently versioned with changelogs documenting why each revision was made. The methods reflection cites specific files, line ranges, and harness check names as evidence for every empirical claim. Inline docstrings explain non-obvious functions, including the rule used to derive confidence levels from the two observable booleans in the schema.

**Evidence in the repo.**

- `prompts/prompt_changelog.md`: documents every revision to the extraction prompt, including the v1.1.0 entry that I deliberately preserved after the revision failed validation, and the re-lock entry explaining why v1.0.0 was restored. This is the kind of changelog a methods reviewer would actually use.
- `schema/schema_changelog.md`: tracks the schema's evolution from v1.0.0 (model-reported confidence) to v1.1.0 (rule-derived confidence with two new required booleans).
- `tracequal/extractor.py`: the `derive_confidence(decision_stated, reasoning_stated) -> str` function carries a docstring stating the rule explicitly ("high if both stated, medium if reasoning inferred, low if decision inferred"), because the rule is the contract and the docstring is where a maintainer will read it.
- `docs/schema_notes.md`: a column-by-column rationale for every field in the decision matrix, citing the methods literature (Feuston and Brubaker 2021, McDonald et al. 2019, Braun and Clarke 2022) that motivates each one.
- `fixtures/real_exports/README.md`: documents what the parser-format test found on real Claude and ChatGPT exports, so a reader who clones the repo without the gitignored exports can still see the result.

**A specific example of documentation-as-judgment.** When the confidence-derivation rule produced a distribution where two-thirds of rows landed in `medium`, I documented the collapse as a finding in the schema notes rather than as a bug to fix. The documentation distinguishes between (a) what the v1 rule does, (b) why it produces the observed distribution, and (c) what a redesign would need to validate before being trusted (multiple fixtures, not the single existing one). The "Confidence rule redesign (unvalidated)" section of `docs/future_work.md` is the result.

---

## C7 — Critical Evaluation and Professional Judgment

**Claim.** Every consequential decision in the build was made by evaluating output before acting on it, and several were made by refusing to act on output that looked correct but wasn't. The harness, the prompt iteration, and the confidence redesign all show this pattern.

**Evidence in the repo.**

The clearest single example is the calibration check. After the rule-based confidence mechanism was added, the harness's calibration check reported that the confidence signal was "not calibrated" because high-confidence rows were correct 67% of the time while the one low-confidence row was correct 100% of the time. The check was mechanically correct: 67% is less than 100%. It was also empirically empty: a 3-versus-1 split cannot support any calibration claim. I rewrote the check to refuse a verdict below a minimum sample size and introduced a new `[N/A]` state in the harness for exactly this case. The final harness reports `[N/A] confidence_calibration_signal — Insufficient data for calibration verdict: high n=3, low n=1, minimum per bucket=5`. The relevant code is in `scripts/validate_extraction.py`; the rationale is in `docs/methods_reflection.md` under Finding 3.

A second example is the prompt revision. After harness validation showed prompt v1.1.0 produced 10 PASS versus v1.0.0's 12 PASS, with none of the four targeted failures fixed, I reverted to v1.0.0 rather than continue iterating. The unsuccessful v1.1.0 prompt and its cached extraction are both committed to the repository as evidence. This is documented in `prompts/prompt_changelog.md` and forms Finding 1 of the reflection.

A third example is the confidence rule redesign. The medium-collapse looked like a problem to fix. The honest analysis was that a redesign tuned to make the distribution look better on the single synthetic fixture would be overfitting to an n-of-1. I locked the v1 rule and specified the redesign as future work with an explicit requirement that any future rule must validate against multiple independent fixtures. The "Confidence rule redesign (unvalidated)" section of `docs/future_work.md` records this decision.

---

## C3 — Data Cleaning and File Handling

**Claim.** The tool reads real exports from external systems (Claude account exports, ChatGPT account exports, and synthetic markdown fixtures) and handles a documented spectrum of format-handling outcomes: clean parses, structurally unsupported formats, and graceful failures. The parser was tested on real account exports from both Claude and ChatGPT, and the support boundary was documented honestly rather than papered over.

**Evidence in the repo.**

- `tracequal/parser.py`: the `parse_chat` function dispatches by file extension and supports Claude's flat `chat_messages` list and the markdown fixture format. Format detection is extension-based (not content-based) to fail loudly rather than guess wrong.
- `scripts/test_parser_formats.py`: a separate test harness that runs `parse_chat` on real exports and reports parse success, turn counts, and speaker attribution. It degrades gracefully when the gitignored real-export files are absent, so a reader who clones the repo without those files still sees an informative message.
- `fixtures/real_exports/README.md`: documents the test result. The Claude export parsed correctly into 8 turns (4 researcher, 4 assistant, alternating, no malformed text). The ChatGPT export failed cleanly at JSON dispatch with `ValueError: Unsupported JSON transcript list format` because ChatGPT stores messages as a tree-structured `mapping` keyed by node id rather than a flat list.
- `README.md` "Supported input formats" section: states precisely which formats are tested-and-supported, which are claimed-but-untested, and which are known-unsupported, so a user choosing input format can make an informed decision.

**A specific traceback I read and diagnosed.** When the validation harness re-ran after the prompt v1.1.0 revision, the report header still printed `Prompt: 1.0.0` even though I had bumped the prompt file to 1.1.0. The diagnostic showed that `get_prompt_schema_version()` was matching the regex `"Schema version\s*\|\s*([0-9]+\.[0-9]+\.[0-9]+)"` against the prompt file. The regex was correct for the row it was matching; the function name was wrong about which row it was returning. I split the function into two honestly-named helpers and made the cache key version-aware so future prompt revisions would not silently return stale extractions. The episode is in `prompts/prompt_changelog.md` (the v1.0.1 entry) and discussed in the reflection as a small but consequential provenance bug.
