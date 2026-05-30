# Methods Reflection: What TraceQual v1 Captures and What It Misses

This document accompanies the v1 release of TraceQual, a disclosure scaffold for solo qualitative researchers using LLMs mid-analysis. It reports what the validation harness found, what those findings mean for the tool's reliability claims, and what they suggest more broadly about audit trails for AI-assisted qualitative work. It is intended for two audiences: methods reviewers evaluating output produced with the tool, and researchers deciding whether to use it.

The reflection is grounded in the synthetic fixture at `docs/synthetic_chat_long.md`, the cached extraction runs in `outputs/`, the validation harness at `scripts/validate_extraction.py`, and the parser format test at `scripts/test_parser_formats.py`. Every claim below can be verified against those artifacts.

A note on continuity. TraceQual extends a line of work, represented in a CSCW submission currently under review, on how people integrate AI into existing communicative and professional practice. Where that study examines how people disclose or conceal AI use in messaging, this tool turns the same question inward: how a researcher's own AI use during analysis can be made visible and inspectable. Both treat AI integration as a practice to be documented rather than a capability to be celebrated or feared.

## What the harness measures

The validation harness runs a battery of checks against the extractor's output, drawing expected behavior from a metadata block at the bottom of the fixture (`Notes for fixture users`). Each check returns one of four states: PASS (expected behavior observed), FAIL (expected behavior absent or contradicted), PENDING (implementation deferred, currently the three positioning-log checks), or N/A (a verdict the harness declines to render because the data cannot support it, currently the calibration checks). Exit code reflects FAIL count only; PENDING and N/A do not block.

The four-state design is itself a small methodological commitment. A harness that could only pass or fail would be forced to render verdicts on questions it cannot answer, which is the exact failure mode this project exists to surface. PENDING and N/A let the harness be honest about the boundary between what it has tested and what it has not.

The fixture covers all five values of the `decision` enum, a coding-to-theming phase transition, three administrative or out-of-scope skip patterns, low-confidence cases, and three positioning-log entries. It was constructed deliberately to exercise the schema's edge cases, not to flatter the extractor.

## What v1 captures reliably

Three categories of behavior pass robustly across multiple runs at the locked configuration:

The `analytic_stage` enum performs well. The extractor correctly identifies the coding-to-theming transition at turn 39 and assigns the majority of rows to `coding` as the working phase. This matters because Braun and Clarke's phase model is the most theoretically loaded component of the schema, and an extractor that confused phases would produce a matrix with no methodological value.

The `decision_enum_deferred` and `decision_enum_unclear` values are detected when the fixture presents them. These are the most theoretically interesting decision categories because they capture analytic moves that simpler binary accept-or-reject schemas would erase. The extractor preserves them.

The parser handles its native input format correctly on real data, not only on the synthetic fixture. A real Claude account export containing a test conversation parsed into exactly the expected eight turns, four researcher and four assistant, alternating, with no malformed text (see `scripts/test_parser_formats.py` and `fixtures/real_exports/README.md`).

## What v1 misses

Two failure modes persisted across every validation run, at both prompt versions:

The extractor generates rows for turns 27 and 47 that should be skipped. Turn 27 is a researcher course-correcting the AI's earlier read; turn 47 is an out-of-scope skip. Both are administrative or transitional rather than analytic, and the schema is explicit that such turns should not produce rows. The persistence of these failures across prompt versions indicates the extractor is biased toward inclusion: when anything happens in a turn, the default action is to emit a row, even when the turn is not an analytic decision about the data. A researcher using TraceQual should expect to review the matrix for spurious rows at points where they were managing the AI rather than coding.

The detection of implicit rejection is unreliable. At turn 35-36 the researcher accepts a code but signals they will handle one dimension of it (valence) outside the AI workflow, which the schema treats as a partial rejection. The extractor does not consistently capture this. Subtle decisions that take the surface form of acceptance are where the tool is weakest.

## Three findings about LLM-assisted extraction

The persistent failures matter, but three findings from the build history matter more, because each generalizes beyond this tool.

### Finding 1: Prompt revisions are not monotonically improving

A revision from prompt v1.0.0 to v1.1.0 was made to address four specific failures (the two skip failures above, plus the accepted and rejected enum counts). The revision added an explicit inclusion criterion, an implicit-rejection rule, and three negative examples drawn from the fixture. The result on the harness: total passes fell from 12 to 10, two previously-passing checks flipped to failures, and none of the four targeted failures was fixed. The revision was reverted. Both prompt versions and both cached extractions are preserved in the repository.

The general point: targeted prompt revisions to fix specific LLM extraction failures can suppress correct behavior elsewhere without fixing the target. The intuition that more-explicit instructions yield better extraction is not reliable. Researchers who revise prompts mid-study must validate against held-out examples, not only the cases they were trying to fix.

### Finding 2: Model non-determinism is comparable in magnitude to prompt-revision effects

The original v1.0.0 cache was overwritten during iteration and regenerated with a second extraction. Same prompt, same model, same temperature 0, same fixture. The two runs differed in row count (22 versus 23 rows) and in four individual check outcomes (`matrix_row_count`, `decision_enum_accepted`, `decision_enum_rejected`, `low_confidence_t38` all flipped between the runs). The identical headline pass count, 12, masked four flips underneath it.

Temperature 0 is widely read as "deterministic." It is not. Claude's outputs at temperature 0 are not bit-identical across runs, owing to batching effects and floating-point non-associativity on GPUs. For a tool whose central claim is to produce auditable trails, this is consequential: a TraceQual matrix is properly understood as one sample from a distribution, not a deterministic transformation of the input. The variance between two runs of the same prompt was comparable to the variance between two different prompts, which means a single run cannot tell a researcher whether a prompt change helped.

Two implications follow. First, researchers should not treat a single extraction as authoritative; either run extraction several times and report the spread, or state in the methods section that the matrix is one realization. Second, audit trails should record the run, not just the configuration. The cache currently encodes prompt, schema, and model versions but not a run identifier, so the two v1.0.0 runs are indistinguishable by filename. A future version should append a run UUID and timestamp, and cache files should be append-only rather than overwriteable.

### Finding 3: A reasoning-grounded confidence signal collapses toward the middle

The confidence field was redesigned during the build. It originally asked the model to self-report `high`, `medium`, or `low`, which is poorly calibrated in general. It was changed to a rule-based derivation computed in Python from two observable booleans: whether the researcher's decision was explicitly stated, and whether their reasoning was explicitly stated. `high` requires both stated, `medium` is decision-stated with reasoning inferred, `low` is decision inferred.

On the fixture, the derived distribution was high=5, medium=14, low=3 across 22 rows. Roughly two-thirds of rows landed in `medium`. The cause is a real property of the interaction: in coding sessions researchers state their decisions explicitly ("accept," "code it differently") but usually leave their reasoning implicit. So `decision_stated` is almost always true while `reasoning_stated` is usually false, and the rule funnels most rows into `medium`. A flag where two-thirds of rows carry the same value gives a reviewer little to triage on.

This is a finding about the data-generating practice, not a bug. Any confidence signal keyed on whether reasoning was stated will mostly return "not stated," because that is how researchers talk to AI mid-analysis. The v1 rule is locked with this limitation documented; a redesign is specified in `docs/future_work.md` and is explicitly unvalidated, because the single synthetic fixture cannot validate a new rule without overfitting to an n-of-1 test case.

A related discipline point: the harness's own calibration check initially tried to declare the confidence signal "not calibrated" from a 3-versus-1 split of high- against low-confidence rows. That is a verdict from four data points, the precise overclaim-from-thin-data error the tool is meant to expose. The check was changed to withhold any calibration verdict below a minimum per-bucket sample and to report the raw counts as descriptive only. The harness now refuses to say more than its data supports.

## Limitations of this reflection

Four limitations are worth naming.

The fixture is synthetic. The behaviors above were observed on a constructed transcript designed to exercise the schema, not on real research sessions. Real data may show different variance and different failure modes. A second-round evaluation on de-identified researcher chat logs, with IRB approval, would be a productive next step.

The positioning pass is unimplemented. Three harness checks are PENDING because `tracequal/positioning.py` raises `NotImplementedError`. The reflection speaks only to the primary decision matrix; whether TraceQual captures epistemic positioning shifts is untested.

Input-format handling is tested on a bounded set. The parser is validated on the markdown fixture format and on a real Claude account export. A real ChatGPT account export was tested and is known to be unsupported in v1: it stores messages as a tree-structured `mapping` rather than a flat list, and the parser fails cleanly at dispatch. ChatGPT users are directed to the paste path, which is format-agnostic. The generic `messages` JSON shape the parser claims to support has not been tested on a real export.

The harness expectations are a judgment call. The fixture's metadata block encodes one researcher's reading of what the extractor should produce. A different qualitative researcher might mark different turns as administrative or disagree about which decisions count as modified rather than accepted. The harness measures alignment with one reading, not absolute accuracy.

## What this means for using TraceQual

Three practical guides for a researcher considering the v1 tool:

Treat the matrix as a draft, not a record. Review every row before exporting, with particular attention to runs of `accepted` rows and to any cluster of skippable administrative turns, given the extractor's inclusion bias.

Record the full configuration and the run. Note prompt version, schema version, model version, and run timestamp alongside any TraceQual matrix. The cache filename encodes the first three; the timestamp currently requires a manual note.

Do not present a TraceQual matrix as evidence of rigor. It is a record of analytic decisions, valuable because it is inspectable, not because it is authoritative. A reviewer should be able to see what the researcher decided and why; they should not infer that using the tool made the analysis better.

## What this means more broadly

TraceQual was built on the premise that audit trails for AI-assisted qualitative analysis are valuable. The v1 findings sharpen rather than contradict that premise. An audit trail is valuable to the degree that the tool producing it is honest about its own limits. A scaffold that produced clean, deterministic, complete matrices would be more attractive and less truthful. This tool documents its failure modes, preserves an unsuccessful iteration, surfaces temperature-0 non-determinism as a property of the workflow, shows where a reasoning-grounded confidence signal loses power, and bounds its own input-format support. That posture, more than the artifact, is the contribution.

## Citations

Braun, V., & Clarke, V. (2006). Using thematic analysis in psychology. *Qualitative Research in Psychology*, 3(2), 77-101.

Braun, V., & Clarke, V. (2022). *Thematic Analysis: A Practical Guide*. SAGE Publications.

Feuston, J. L., & Brubaker, J. R. (2021). Putting Tools in Their Place: The Role of Time and Perspective in Human-AI Collaboration for Qualitative Analysis. *Proceedings of the ACM on Human-Computer Interaction*, 5(CSCW2), 1-25. [https://doi.org/10.1145/3479856](https://doi.org/10.1145/3479856)

McDonald, N., Schoenebeck, S., & Forte, A. (2019). Reliability and Inter-rater Reliability in Qualitative Research: Norms and Guidelines for CSCW and HCI Practice. *Proceedings of the ACM on Human-Computer Interaction*, 3(CSCW), 1-23. [https://doi.org/10.1145/3359174](https://doi.org/10.1145/3359174)  
