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
