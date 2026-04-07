from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


OBJECT_STATUS_CREATED = "created"
OBJECT_STATUS_INSTALLED = "installed"
OBJECT_STATUS_RUNNING = "running"
OBJECT_STATUS_STOPPED = "stopped"
OBJECT_STATUS_REMOVED = "removed"
OBJECT_STATUS_ERROR = "error"

OBJECT_STATUS_INSTALL_FAILED_PRESERVED = "install_failed_preserved"
OBJECT_STATUS_START_FAILED_PRESERVED = "start_failed_preserved"

OBJECT_NORMAL_STATUSES = frozenset(
    {
        OBJECT_STATUS_INSTALLED,
        OBJECT_STATUS_RUNNING,
        OBJECT_STATUS_STOPPED,
    }
)
OBJECT_FAILURE_PRESERVED_STATUSES = frozenset(
    {
        OBJECT_STATUS_INSTALL_FAILED_PRESERVED,
        OBJECT_STATUS_START_FAILED_PRESERVED,
    }
)
OBJECT_CLEARABLE_STATUSES = frozenset(OBJECT_FAILURE_PRESERVED_STATUSES)
OBJECT_RESETTABLE_STATUSES = frozenset(
    {
        OBJECT_STATUS_INSTALLED,
        OBJECT_STATUS_RUNNING,
        OBJECT_STATUS_STOPPED,
        OBJECT_STATUS_INSTALL_FAILED_PRESERVED,
        OBJECT_STATUS_START_FAILED_PRESERVED,
    }
)


def _now_iso() -> str:
    return datetime.now().isoformat()


def is_failure_preserved_object_status(status: str) -> bool:
    return status in OBJECT_FAILURE_PRESERVED_STATUSES


def is_normal_object_status(status: str) -> bool:
    return status in OBJECT_NORMAL_STATUSES


def is_clearable_object_status(status: str) -> bool:
    return status in OBJECT_CLEARABLE_STATUSES


def is_resettable_object_status(status: str) -> bool:
    return status in OBJECT_RESETTABLE_STATUSES


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
    status: str = OBJECT_STATUS_CREATED
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
class InstallationSourceAsset:
    product: str
    version: str
    source_type: str
    path: str
    checksum_type: str = ""
    checksum_value: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InstallationSourceAsset":
        return cls(**data)


@dataclass
class DependencyAsset:
    name: str
    path: str
    asset_type: str = "library"
    required: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DependencyAsset":
        return cls(**data)


@dataclass
class MySQLLifecycleScenarioConfig:
    scenario_name: str
    product: str
    version: str
    workspace_path: str
    instance_name: str
    port: int
    runtime_backend: str = "host"
    directories: dict[str, str] = field(default_factory=dict)
    database_name: str = "ptest_mysql"
    table_name: str = "crud_items"
    boundary_checks: dict[str, bool] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MySQLLifecycleScenarioConfig":
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
