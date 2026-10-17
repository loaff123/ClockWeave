"""Admission defaults selected from measured workloads, not OS guarantees."""
from dataclasses import dataclass
from .model import ClockWeaveError

@dataclass(frozen=True)
class Limits:
    max_input_bytes: int = 8 * 1024 * 1024
    max_spans: int = 10_000
    max_domain_epochs: int = 64

DEFAULT_LIMITS = Limits()


def admit(value: int,maximum: int,label: str) -> None:
    if value>maximum:
        raise ClockWeaveError('limit_exceeded','admission_limit',f'{label} ({value}) exceeds the measured default admission limit ({maximum}); no partial diagnosis was produced.')
