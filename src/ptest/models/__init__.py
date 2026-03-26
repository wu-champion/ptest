from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


def _now_iso() -> str:
    return datetime.now().isoformat()


@dataclass
class EnvironmentRecord:
    root_path: str
    status: str = "ready"
    isolation_level: str = "basic"
    config_file: str = "ptest_config.json"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EnvironmentRecord":
        return cls(**data)


@dataclass
class ManagedObjectRecord:
    name: str
    type_name: str
    status: str = "created"
    installed: bool = False
    config: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ManagedObjectRecord":
        return cls(**data)


@dataclass
class ToolRecord:
    name: str
    status: str = "created"
    installed: bool = False
    config: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolRecord":
        return cls(**data)


@dataclass
class ExecutionRecord:
    execution_id: str
    case_id: str
    status: str
    duration: float
    start_time: str
    end_time: str
    error_message: str = ""
    output: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecutionRecord":
        return cls(**data)


@dataclass
class ProblemRecord:
    problem_id: str
    problem_type: str
    summary: str
    status: str = "open"
    preservation_status: str = "success"
    execution_id: str = ""
    case_id: str = ""
    environment_id: str = ""
    object_refs: list[str] = field(default_factory=list)
    artifact_refs: dict[str, Any] = field(default_factory=dict)
    log_refs: dict[str, Any] = field(default_factory=dict)
    latest_action: str = "preserved"
    notes: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProblemRecord":
        return cls(**data)


@dataclass
class ProblemAssetRecord:
    problem_id: str
    problem_type: str
    summary: str
    status: str = "open"
    preservation_status: str = "success"
    execution_id: str = ""
    case_id: str = ""
    environment_id: str = ""
    object_refs: list[str] = field(default_factory=list)
    artifact_refs: dict[str, Any] = field(default_factory=dict)
    log_refs: dict[str, Any] = field(default_factory=dict)
    recovery: dict[str, Any] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProblemAssetRecord":
        return cls(**data)


@dataclass
class ProblemRecoveryRecord:
    action_id: str
    problem_id: str
    problem_type: str
    action_type: str
    mode: str
    success: bool
    status: str
    execution_id: str = ""
    case_id: str = ""
    environment_id: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProblemRecoveryRecord":
        return cls(**data)
