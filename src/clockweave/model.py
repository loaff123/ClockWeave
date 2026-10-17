"""Data structures shared by public entry points."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

@dataclass(frozen=True)
class InputSource:
    path: Path
    format: str = 'auto'

@dataclass(frozen=True)
class SourceRef:
    file_sha256: str
    file_name: str
    document_index: int
    line: int | None
    json_pointer: str

class ClockWeaveError(ValueError):
    def __init__(self, kind: str, code: str, message: str, source: SourceRef | None = None):
        super().__init__(message)
        self.kind, self.code, self.message, self.source = kind, code, message, source

@dataclass(frozen=True)
class Span:
    key: tuple[str, str]
    name: str
    kind: int
    parent: tuple[str, str] | None
    start_ns: int | None
    end_ns: int | None
    resource: dict[str, Any]
    attributes: dict[str, Any]
    scope_name: str
    scope_version: str
    warnings: tuple
    sources: tuple[SourceRef, ...]
    issues: tuple[str, ...]

@dataclass(frozen=True)
class Capture:
    spans: tuple[Span, ...]
    inputs: tuple[dict, ...]
    duplicate_observations: int = 0

@dataclass(frozen=True)
class Contract:
    data: dict
    sha256: str
    canonical_sha256: str

@dataclass(frozen=True)
class Constraint:
    id: str
    from_id: str
    to_id: str
    weight_ns: int
    relation: str
    boundary_id: str
    client: tuple[str, str]
    server: tuple[str, str]
    endpoint_values_ns: tuple[int, int]
    slack_ns: int
    sources: tuple[SourceRef, ...]

@dataclass(frozen=True)
class Extraction:
    variables: tuple[dict, ...]
    anchor: str | None
    constraints: tuple[Constraint, ...]
    coverage: dict
    qualification: dict
    reasons: tuple[dict, ...]
