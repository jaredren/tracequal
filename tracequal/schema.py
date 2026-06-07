"""Load and validate TraceQual decision matrix and positioning log data.

A "schema" is a written-down description of what valid data must look like (which
fields exist, their types, allowed values). This module loads that schema from a
file and uses it to check that our data obeys the rules — catching mistakes early.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema  # third-party library implementing the JSON Schema standard
from jsonschema import Draft202012Validator, ValidationError

# Figure out where this project lives on disk, relative to this very file.
# __file__ is the path to schema.py; .resolve() makes it absolute; .parent goes
# up one folder. So PACKAGE_ROOT = the "tracequal/" package, PROJECT_ROOT = repo root.
PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent
DEFAULT_SCHEMA_PATH = PROJECT_ROOT / "schema" / "decision_matrix_v1.json"

# Type aliases that give plain dicts/lists meaningful names. They don't change
# behavior — they make function signatures below easier to read.
DecisionRow = dict[str, Any]  # one row of the decision matrix
PositioningRow = dict[str, Any]  # one row of the positioning log
DecisionMatrix = list[DecisionRow]  # the whole decision matrix (a list of rows)
PositioningLog = list[PositioningRow]  # the whole positioning log
SchemaDocument = dict[str, Any]  # the parsed schema file itself


class SchemaVersionError(ValueError):
    """Raised when an instance version does not match the loaded schema.

    Defining our own exception type lets callers catch this specific problem
    (version mismatch) separately from other errors.
    """


def load_schema(path: Path | str | None = None) -> SchemaDocument:
    """Load the TraceQual JSON Schema document from disk."""
    # If no path is given, fall back to the project's default schema location.
    schema_path = Path(path) if path is not None else DEFAULT_SCHEMA_PATH
    # `with ... as handle:` opens the file and guarantees it gets closed afterward.
    with schema_path.open(encoding="utf-8") as handle:
        return json.load(handle)  # parse the JSON file into a Python dict


def get_schema_version(schema: SchemaDocument | None = None) -> str:
    """Return the TraceQual schema version string (e.g. "1.0.0")."""
    # Use the schema passed in, or load the default one if none was provided.
    document = schema if schema is not None else load_schema()
    return str(document["tracequal_version"])


def _validator(schema: SchemaDocument) -> Draft202012Validator:
    """Build a JSON Schema validator that resolves ``$ref`` from the full document.

    A "validator" is an object that knows how to check data against the schema.
    We build it from the whole document so internal references ($ref) resolve.
    """
    return Draft202012Validator(schema)


def validate_decision_row(row: DecisionRow, schema: SchemaDocument | None = None) -> None:
    """Validate a single decision matrix row.

    Raises a ValidationError if the row breaks the rules; returns None if it's OK.
    """
    document = schema if schema is not None else load_schema()
    # "$defs" holds reusable sub-schemas by name; grab the one for a single row.
    subschema = document["$defs"]["decision_row"]
    _validator(document).validate(row, subschema)


def validate_decision_matrix(
    rows: DecisionMatrix,
    schema: SchemaDocument | None = None,
    *,
    expected_version: str | None = None,
) -> None:
    """Validate a decision matrix array against the loaded schema.

    The optional ``expected_version`` lets a caller insist on a specific schema
    version and fail loudly if the loaded schema is a different one.
    """
    document = schema if schema is not None else load_schema()
    # Optional safety check: confirm we're using the schema version the caller wants.
    if expected_version is not None and expected_version != document["tracequal_version"]:
        raise SchemaVersionError(
            f"Expected schema version {expected_version!r}, "
            f"got {document['tracequal_version']!r}."
        )
    subschema = document["$defs"]["decision_matrix"]
    _validator(document).validate(rows, subschema)


def validate_positioning_row(
    row: PositioningRow,
    schema: SchemaDocument | None = None,
) -> None:
    """Validate a single positioning log row."""
    document = schema if schema is not None else load_schema()
    subschema = document["$defs"]["positioning_row"]
    _validator(document).validate(row, subschema)


def validate_positioning_log(
    rows: PositioningLog,
    schema: SchemaDocument | None = None,
) -> None:
    """Validate a positioning log array against the loaded schema."""
    document = schema if schema is not None else load_schema()
    subschema = document["$defs"]["positioning_log"]
    _validator(document).validate(rows, subschema)


def format_validation_error(error: ValidationError) -> str:
    """Return a concise, human-readable validation error message.

    A raw ValidationError can be verbose. This pulls out just the message and the
    location of the problem (e.g. "0.confidence") for a friendlier one-liner.
    """
    # absolute_path is a sequence of keys/indexes pointing at the bad value;
    # join them with dots so "rows[0]['confidence']" reads as "0.confidence".
    path = ".".join(str(part) for part in error.absolute_path)
    location = f" at {path}" if path else ""
    return f"{error.message}{location}"
