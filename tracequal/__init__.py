"""TraceQual: disclosure scaffold for AI-assisted qualitative analysis.

This file makes the ``tracequal`` folder a Python "package". The imports below
re-export the most useful functions/classes so callers can write, e.g.,
``from tracequal import extract_decisions`` instead of the longer
``from tracequal.extractor import extract_decisions``.
"""

# Pull the public names up from their individual modules into this top-level package.
from tracequal.extractor import extract_decisions
from tracequal.parser import Turn, format_transcript, parse_chat, parse_chat_content
from tracequal.positioning import extract_positioning
from tracequal.schema import (
    SchemaVersionError,
    get_schema_version,
    load_schema,
    validate_decision_matrix,
    validate_decision_row,
    validate_positioning_log,
)

# `__all__` lists the names considered this package's public API. It controls
# what `from tracequal import *` brings in, and documents intended entry points.
__all__ = [
    "SchemaVersionError",
    "Turn",
    "extract_decisions",
    "extract_positioning",
    "format_transcript",
    "get_schema_version",
    "load_schema",
    "parse_chat",
    "parse_chat_content",
    "validate_decision_matrix",
    "validate_decision_row",
    "validate_positioning_log",
]
