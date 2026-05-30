"""Secondary epistemic positioning pass for TraceQual."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tracequal.parser import Turn
from tracequal.schema import DecisionMatrix, PositioningLog

NOT_IMPLEMENTED_MESSAGE = (
    "Positioning pass not yet implemented. "
    "See docs/project_structure.md and docs/schema_notes.md "
    "(Secondary table: positioning_log)."
)


def extract_positioning(
    turns: list[Turn],
    decisions: DecisionMatrix,
    prompt_path: Path | str | None = None,
    **kwargs: Any,
) -> PositioningLog:
    """Run the secondary epistemic positioning pass on a parsed transcript.

    Takes the original transcript turns and the primary decision matrix,
    then returns a sparse positioning log of stance shifts.

    Args:
        turns: Parsed chat transcript turns.
        decisions: Validated decision matrix from the primary extraction pass.
        prompt_path: Optional path to ``prompts/positioning_pass.md``.
        **kwargs: Reserved for future API and caching options.

    Returns:
        A list of positioning log rows matching ``$defs/positioning_log``.

    Raises:
        NotImplementedError: Until the positioning prompt and API wrapper exist.
    """
    raise NotImplementedError(NOT_IMPLEMENTED_MESSAGE)
