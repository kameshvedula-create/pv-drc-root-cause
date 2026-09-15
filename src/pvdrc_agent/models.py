from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping


class RootCause(str, Enum):
    ROUTING_CONGESTION = "routing_congestion"
    SHORT_JOG = "short_jog"
    PIN_ACCESS = "pin_access"
    FIXED_OBSTRUCTION = "fixed_obstruction"
    VIA_PROXIMITY = "via_proximity"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ViolationCase:
    violation_id: str
    rule_id: str
    layer: str
    bbox: tuple[float, float, float, float]
    features: Mapping[str, float | int | bool | str] = field(default_factory=dict)
    protected_objects: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Diagnosis:
    root_cause: RootCause
    confidence: float
    rationale: tuple[str, ...] = ()


@dataclass(frozen=True)
class RepairCandidate:
    repair_id: str
    action: str
    parameters: Mapping[str, float | int | bool | str] = field(default_factory=dict)
    touched_objects: frozenset[str] = frozenset()
    edit_cost: float = 0.0
    risk: float = 0.0


@dataclass(frozen=True)
class ValidationReport:
    violation_signatures: frozenset[str]
    target_present: bool
    protected_objects_modified: frozenset[str] = frozenset()

    @property
    def total_violations(self) -> int:
        return len(self.violation_signatures)


@dataclass(frozen=True)
class AgentConfig:
    confidence_threshold: float = 0.70
    max_attempts: int = 3


@dataclass(frozen=True)
class AgentResult:
    status: str
    violation_id: str
    diagnosis: Diagnosis
    chosen_repair: RepairCandidate | None = None
    attempts: int = 0
    reason: str = ""
    before_count: int = 0
    after_count: int = 0
