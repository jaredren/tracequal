"""Load and validate TraceQual decision matrix and positioning log data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
from jsonschema import Draft202012Validator, ValidationError

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent
DEFAULT_SCHEMA_PATH = PROJECT_ROOT / "schema" / "decision_matrix_v1.json"

DecisionRow = dict[str, Any]
PositioningRow = dict[str, Any]
DecisionMatrix = list[DecisionRow]
PositioningLog = list[PositioningRow]
SchemaDocument = dict[str, Any]


class SchemaVersionError(ValueError):
    """Raised when an instance version does not match the loaded schema."""


def load_schema(path: Path | str | None = None) -> SchemaDocument:
    """Load the TraceQual JSON Schema document from disk."""
    schema_path = Path(path) if path is not None else DEFAULT_SCHEMA_PATH
    with schema_path.open(encoding="utf-8") as handle:
        return json.load(handle)


def get_schema_version(schema: SchemaDocument | None = None) -> str:
    """Return the TraceQual schema version string."""
    document = schema if schema is not None else load_schema()
    return str(document["tracequal_version"])


def _validator(schema: SchemaDocument) -> Draft202012Validator:
    """Build a JSON Schema validator that resolves ``$ref`` from the full document."""
    return Draft202012Validator(schema)


def validate_decision_row(row: DecisionRow, schema: SchemaDocument | None = None) -> None:
    """Validate a single decision matrix row."""
    document = schema if schema is not None else load_schema()
    subschema = document["$defs"]["decision_row"]
    _validator(document).validate(row, subschema)


def validate_decision_matrix(
    rows: DecisionMatrix,
    schema: SchemaDocument | None = None,
    *,
    expected_version: str | None = None,
) -> None:
    """Validate a decision matrix array against the loaded schema."""
    document = schema if schema is not None else load_schema()
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
    """Return a concise, human-readable validation error message."""
    path = ".".join(str(part) for part in error.absolute_path)
    location = f" at {path}" if path else ""
    return f"{error.message}{location}"
