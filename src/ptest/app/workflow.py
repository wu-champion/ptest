from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import socket
import sqlite3
import time
import uuid
from datetime import datetime
from pathlib import Path
import shutil
from typing import Any, Literal, cast

from ..cases.manager import CaseManager
from ..cases.result import TestCaseResult
from ..assertions.factory import AssertionFactory
from ..config import DEFAULT_CONFIG
from ..contract.manager import ContractManager
from ..data.generator import DataGenerationConfig, DataGenerator, DataTemplate
from ..environment import EnvironmentManager
from ..isolation.manager import IsolationManager
from ..models import (
    DependencyAsset,
    EnvironmentRecord,
    ExecutionRecord,
    InstallationSourceAsset,
    ManagedObjectRecord,
    MySQLLifecycleScenarioConfig,
    OBJECT_STATUS_CREATED,
    OBJECT_STATUS_ERROR,
    OBJECT_STATUS_INSTALL_FAILED_PRESERVED,
    OBJECT_STATUS_INSTALLED,
    PROBLEM_ACTION_PRESERVED,
    PROBLEM_PRESERVATION_FAILED,
    PROBLEM_PRESERVATION_PARTIAL,
    PROBLEM_PRESERVATION_SUCCESS,
    PROBLEM_STATUS_OPEN,
    OBJECT_STATUS_REMOVED,
    OBJECT_STATUS_RUNNING,
    OBJECT_STATUS_START_FAILED_PRESERVED,
    OBJECT_STATUS_STOPPED,
    ToolRecord,
    WorkspaceBaselineRecord,
    is_clearable_object_status,
    is_failure_preserved_object_status,
    is_resettable_object_status,
)
from ..models import ProblemAssetRecord, ProblemRecord, ProblemRecoveryRecord
from ..mock import MockConfig, MockServer
from ..objects.manager import ObjectManager
from ..reports.generator import ReportGenerator
from ..suites import SuiteManager
from ..storage import WorkspaceStorage
from ..tools.manager import ToolManager

_resource: Any
try:
    import resource as _resource
except ImportError:
    _resource = None

PROBLEM_ALLOWED_STATUSES: set[str] = {
    "open",
    "investigating",
    "resolved",
    "closed",
}


class _ReplayResponseView:
    def __init__(self, status_code: int, headers: dict[str, Any], body: Any) -> None:
        self.status_code = status_code
        self.headers = headers
        self._body = body
        if isinstance(body, str):
            self.text = body
        elif isinstance(body, (dict, list)):
            self.text = json.dumps(body, ensure_ascii=False, sort_keys=True)
        else:
            self.text = str(body)

    def json(self) -> Any:
        if isinstance(self._body, str):
            raise ValueError("response body is not json")
        return self._body


class WorkflowService:
    """First-phase workflow orchestration service."""

    DEFAULT_MANAGED_MYSQL_PORT = 13306
    WORKSPACE_BASELINE_CONTENT_MAX_BYTES = 256 * 1024
    WORKSPACE_BASELINE_CONTENT_MAX_FILES = 32
    OBJECT_ARTIFACT_MAX_SCAN_FILES = 500
    OBJECT_ARTIFACT_MAX_SCAN_DEPTH = 4
    OBJECT_ARTIFACT_LATEST_FILE_LIMIT = 5

    def __init__(
        self,
        root_path: str | Path | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.root_path = Path(root_path or Path.cwd()).resolve()
        self.config = config.copy() if config else DEFAULT_CONFIG.copy()
        self.storage = WorkspaceStorage(self.root_path)
        self._isolation_manager: IsolationManager | None = None
        self._mock_servers: dict[str, MockServer] = {}

    def init_environment(self, path: str | Path | None = None) -> EnvironmentRecord:
        if path is not None:
            self.root_path = Path(path).resolve()
            self.storage = WorkspaceStorage(self.root_path)
        existing = self.storage.load_environment()
        try:
            env_manager = self._bootstrap_environment()
            isolation_metadata = self._ensure_isolation_environment(existing)
            default_isolation_level = self.config.get(
                "default_isolation_level", "basic"
            )
            isolation_level = (
                default_isolation_level
                if isinstance(default_isolation_level, str)
                else "basic"
            )
            record = EnvironmentRecord(
                root_path=str(self.root_path),
                status="ready",
                isolation_level=isolation_level,
                config_file="ptest_config.json",
                created_at=existing.created_at
                if existing
                else datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
                metadata={
                    "reports_dir": str(env_manager.report_dir),
                    "logs_dir": str(env_manager.log_dir),
                    "dumps_dir": str(env_manager.dump_dir),
                    "isolation": isolation_metadata,
                    "runtime_backend": self._build_runtime_backend_capability("host"),
                    "crash_capture": self._build_environment_crash_capture_capability(
                        env_manager.dump_dir
                    ),
                },
            )
            return self.storage.save_environment(record)
        except Exception as exc:
            self._record_environment_dependency_problem(
                problem_type="environment_init",
                summary=f"Environment initialization problem at '{self.root_path}'",
                details={
                    "phase": "init",
                    "root_path": str(self.root_path),
                    "error": str(exc),
                    "existing_environment": existing.to_dict() if existing else None,
                },
                recovery={
                    "supported": False,
                    "mode": "minimal_environment_recovery",
                    "root_path": str(self.root_path),
                    "action": "reinitialize_environment",
                },
            )
            raise

    def get_environment_status(self) -> dict[str, Any]:
        record = self.storage.load_environment()
        if record is None:
            return {
                "initialized": False,
                "path": str(self.root_path),
                "objects": 0,
                "cases": 0,
                "reports": 0,
            }

        if record.status == "destroyed":
            return {
                "initialized": False,
                "path": str(self.root_path),
                "status": "destroyed",
                "isolation_level": record.isolation_level,
                "objects": 0,
                "cases": 0,
                "reports": 0,
                "metadata": record.metadata,
            }

        env_manager = self._bootstrap_environment()
        case_manager = CaseManager(env_manager)
        objects = self.storage.load_objects()
        report_count = len(list((self.root_path / "reports").glob("*")))
        return {
            "initialized": True,
            "path": str(self.root_path),
            "status": record.status,
            "isolation_level": record.isolation_level,
            "objects": len(objects),
            "cases": len(case_manager.cases),
            "reports": report_count,
            "metadata": record.metadata,
        }

    def create_workspace_baseline(self, summary: str = "") -> dict[str, Any]:
        environment = self.storage.load_environment()
        if environment is None:
            environment = self.init_environment(self.root_path)
        objects = self.storage.load_objects()
        baseline_id = (
            f"baseline_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
        )
        content_capture = self._build_workspace_baseline_content_snapshots(
            baseline_id,
            objects,
        )
        record = WorkspaceBaselineRecord(
            baseline_id=baseline_id,
            root_path=str(self.root_path),
            summary=summary or "workspace minimum baseline snapshot",
            environment=environment.to_dict(),
            objects=[item.to_dict() for item in objects.values()],
            metadata={
                "object_count": len(objects),
                "capture_scope": "workspace_minimum_baseline",
                "object_reference_snapshots": self._build_workspace_baseline_object_references(
                    objects
                ),
                "content_reference_snapshots": content_capture["snapshots"],
                "content_reference_skipped": content_capture["skipped"],
                "limitations": [
                    "only small explicitly supported content files are copied",
                    "full directory-level copies are not included in this baseline",
                    "full database image restoration is not included in this baseline",
                    "container/system rollback is not included in this first-stage baseline",
                ],
            },
        )
        self.storage.save_workspace_baseline(record)
        return {
            "success": True,
            "status": "created",
            "message": f"Workspace baseline created: {baseline_id}",
            "data": self._build_workspace_baseline_summary(record),
        }

    def list_workspace_baselines(self) -> list[dict[str, Any]]:
        return [
            self._build_workspace_baseline_summary(item)
            for item in self.storage.list_workspace_baselines()
        ]

    def restore_workspace_baseline(self, baseline_id: str) -> dict[str, Any]:
        record = self.storage.get_workspace_baseline(baseline_id)
        if record is None:
            return {
                "success": False,
                "status": "not_found",
                "message": f"Workspace baseline not found: {baseline_id}",
                "error": f"Workspace baseline '{baseline_id}' does not exist",
            }

        environment_data = (
            record.environment if isinstance(record.environment, dict) else {}
        )
        restored_environment = EnvironmentRecord.from_dict(environment_data)
        restored_environment.updated_at = datetime.now().isoformat()
        self.storage.save_environment(restored_environment)

        restored_objects: dict[str, ManagedObjectRecord] = {}
        raw_objects = record.objects if isinstance(record.objects, list) else []
        for item in raw_objects:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                object_record = ManagedObjectRecord.from_dict(item)
                object_record.updated_at = datetime.now().isoformat()
                restored_objects[object_record.name] = object_record
        self.storage.save_objects(restored_objects)
        directory_restore = self._restore_workspace_baseline_object_references(record)
        content_restore = self._restore_workspace_baseline_content_references(record)

        return {
            "success": True,
            "status": "restored",
            "message": f"Workspace baseline restored: {baseline_id}",
            "data": {
                "baseline": self._build_workspace_baseline_summary(record),
                "restored_object_names": sorted(restored_objects.keys()),
                "verification": {
                    "scope": "workspace_minimum_baseline_restore",
                    "restored_object_count": len(restored_objects),
                    "environment_status": restored_environment.status,
                    "directory_restore": directory_restore,
                    "content_restore": content_restore,
                    "next_actions": [
                        "verify_recovered_object_state",
                        "rerun_affected_case_after_baseline_restore",
                    ],
                },
            },
        }

    def install_object(
        self, obj_type: str, name: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        manager = self._get_object_manager()
        install_params = self._normalize_object_install_params(obj_type, name, params)
        normalized_type = manager.normalize_type(obj_type)
        result = manager.install(normalized_type, name, install_params)
        success = result.startswith("✓")
        materialized = manager.get_object(name)
        record_status = (
            OBJECT_STATUS_INSTALLED
            if success
            else self._resolve_install_failure_status(
                normalized_type,
                install_params,
                result,
                materialized,
            )
        )
        record = ManagedObjectRecord(
            name=name,
            type_name=normalized_type,
            status=record_status,
            installed=success,
            config=install_params,
            created_at=self._existing_object_created_at(name),
            updated_at=datetime.now().isoformat(),
            metadata=self._collect_object_metadata(materialized)
            if materialized
            else {},
        )
        record.metadata["runtime_backend"] = self._build_object_runtime_backend_summary(
            record
        )
        record.metadata["crash_capture"] = self._merge_object_crash_capture_capability(
            record,
            record.metadata.get("crash_capture"),
        )
        if record.status == OBJECT_STATUS_INSTALL_FAILED_PRESERVED:
            record.metadata["failure_state"] = self._build_failure_state_metadata(
                phase="install",
                message=result,
            )
        self.storage.upsert_object(record)
        if not success:
            problem_type = self._classify_object_install_problem(
                normalized_type,
                params or {},
                result,
            )
            self._record_environment_dependency_problem(
                problem_type=problem_type,
                summary=f"Dependency object install problem for '{name}'",
                details={
                    "phase": "install",
                    "action": "install",
                    "object": record.to_dict(),
                    "message": result,
                    "provided_params": install_params,
                },
                recovery={
                    "supported": False,
                    "mode": "minimal_environment_recovery",
                    "action": "install_object",
                    "object_name": name,
                    "object_type": normalized_type,
                    "params": install_params,
                },
                object_refs=[name],
            )
        return self._operation_result(
            success=success,
            status=record.status if success else "error",
            message=result,
            data=record.to_dict(),
            object=record.to_dict(),
            error_code="object_install_failed" if not success else None,
        )

    def _normalize_object_install_params(
        self,
        obj_type: str,
        name: str,
        params: dict[str, Any] | None,
    ) -> dict[str, Any]:
        install_params = params.copy() if params else {}
        if obj_type.lower() != "mysql":
            return install_params
        return self._build_mysql_service_install_params(name, install_params)

    def _build_mysql_service_install_params(
        self,
        name: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        workspace_path = Path(params.get("workspace_path", self.root_path)).resolve()
        instance_root = workspace_path / ".ptest" / "managed_objects" / name
        directories = {
            "instance_root": str(instance_root),
            "install_dir": str(instance_root / "install"),
            "data_dir": str(instance_root / "data"),
            "config_dir": str(instance_root / "config"),
            "lib_dir": str(instance_root / "lib"),
            "files_dir": str(instance_root / "mysql-files"),
            "log_dir": str(instance_root / "logs"),
            "run_dir": str(instance_root / "run"),
            "dump_dir": str(instance_root / "dumps"),
        }
        port = self._coerce_mysql_port(
            params.get("port", params.get("server_port")),
        )
        package_path_value = params.get(
            "mysql_package_path", params.get("package_path")
        )
        source_asset = None
        if isinstance(package_path_value, (str, Path)) and str(package_path_value):
            package_path = Path(package_path_value).expanduser().resolve()
            source_asset = InstallationSourceAsset(
                product="mysql",
                version=str(params.get("version", "8.4")),
                source_type=str(params.get("source_type", "archive")),
                path=str(package_path),
                checksum_type=str(params.get("checksum_type", "")),
                checksum_value=str(params.get("checksum_value", "")),
                metadata={
                    "managed_by": "ptest",
                    "scenario_name": "mysql_full_lifecycle",
                },
            )

        scenario = MySQLLifecycleScenarioConfig(
            scenario_name="mysql_full_lifecycle",
            product="mysql",
            version=str(params.get("version", "8.4")),
            workspace_path=str(workspace_path),
            instance_name=name,
            port=port,
            runtime_backend=str(params.get("runtime_backend", "host")),
            directories=directories.copy(),
            boundary_checks={
                "check_workspace_boundary": True,
                "check_process_cleanup": True,
                "check_port_release": True,
                "check_object_cleanup": True,
            },
        )

        normalized = params.copy()
        dependency_assets = self._normalize_mysql_dependency_assets(
            params.get("dependency_assets")
        )
        normalized.update(
            {
                "db_type": "mysql",
                "workspace_path": str(workspace_path),
                "server_host": str(params.get("server_host", "127.0.0.1")),
                "server_port": port,
                "runtime_backend": scenario.runtime_backend,
                "runtime_backend_requirements": self._build_runtime_backend_requirements(
                    "mysql_managed_instance"
                ),
                "instance_name": name,
                "database_name": scenario.database_name,
                "data_dir": directories["data_dir"],
                "config_dir": directories["config_dir"],
                "config_file": str(Path(directories["config_dir"]) / "my.cnf"),
                "log_file": str(Path(directories["log_dir"]) / "mysql.log"),
                "pid_file": str(Path(directories["run_dir"]) / "mysql.pid"),
                "socket_file": str(Path(directories["run_dir"]) / "mysql.sock"),
                "managed_instance": directories,
                "crash_capture": self._build_object_crash_capture_capability(
                    dump_dir=directories["dump_dir"]
                ),
                "dependency_assets": dependency_assets,
                "scenario": scenario.to_dict(),
            }
        )
        if source_asset is not None:
            normalized["mysql_package_path"] = source_asset.path
            normalized["source_asset"] = source_asset.to_dict()
        return normalized

    def _normalize_mysql_dependency_assets(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        assets: list[dict[str, Any]] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            path_value = item.get("path")
            name_value = item.get("name")
            if not isinstance(path_value, (str, Path)) or not str(path_value):
                continue
            asset = DependencyAsset(
                name=str(name_value or Path(str(path_value)).name),
                path=str(Path(path_value).expanduser().resolve()),
                asset_type=str(item.get("asset_type", "library")),
                required=bool(item.get("required", True)),
                metadata=item.get("metadata", {})
                if isinstance(item.get("metadata"), dict)
                else {},
            )
            assets.append(asset.to_dict())
        return assets

    def _coerce_mysql_port(self, value: Any) -> int:
        if isinstance(value, int) and value > 0:
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return self.DEFAULT_MANAGED_MYSQL_PORT

    def start_object(self, name: str) -> dict[str, Any]:
        return self._change_object_state(name, "start")

    def stop_object(self, name: str) -> dict[str, Any]:
        return self._change_object_state(name, "stop")

    def restart_object(self, name: str) -> dict[str, Any]:
        return self._change_object_state(name, "restart")

    def uninstall_object(self, name: str) -> dict[str, Any]:
        record = self.storage.get_object(name)
        if record is None:
            return self._not_found_result("object", name)

        obj = self._materialize_object(record)
        if record.type_name in {"database", "database_server", "database_client"}:
            self._recover_object_runtime(obj, record)
        result = obj.uninstall()
        success = result.startswith("✓")
        metadata = record.metadata.copy()
        metadata.update(self._collect_object_metadata(obj))
        metadata["runtime_backend"] = self._build_object_runtime_backend_summary(record)
        record.metadata = metadata
        record.updated_at = datetime.now().isoformat()
        checks = None
        if success:
            checks = self._collect_mysql_boundary_checks(
                record,
                action="uninstall",
                object_removed=True,
            )
            self.storage.delete_object(name)
        else:
            record.status = "error"
            record.updated_at = datetime.now().isoformat()
            self.storage.upsert_object(record)
        return self._operation_result(
            success=success,
            status="removed" if success else "error",
            message=result,
            data=record.to_dict(),
            checks=checks,
            error_code="object_uninstall_failed" if not success else None,
        )

    def install_tool(
        self, name: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        manager = self._get_tool_manager()
        result = manager.install(name, params or {})
        success = result.startswith("✓")
        record = ToolRecord(
            name=name,
            status="installed" if success else "error",
            installed=success,
            config=params or {},
            created_at=self._existing_tool_created_at(name),
            updated_at=datetime.now().isoformat(),
        )
        self.storage.upsert_tool(record)
        return self._operation_result(
            success=success,
            status=record.status if success else "error",
            message=result,
            data=record.to_dict(),
            tool=record.to_dict(),
            error_code="tool_install_failed" if not success else None,
        )

    def start_tool(self, name: str) -> dict[str, Any]:
        return self._change_tool_state(name, "start")

    def stop_tool(self, name: str) -> dict[str, Any]:
        return self._change_tool_state(name, "stop")

    def restart_tool(self, name: str) -> dict[str, Any]:
        return self._change_tool_state(name, "restart")

    def uninstall_tool(self, name: str) -> dict[str, Any]:
        record = self.storage.get_tool(name)
        if record is None:
            return self._not_found_result("tool", name)
        tool = self._materialize_tool(record)
        result = tool.uninstall()
        success = result.startswith("✓")
        if success:
            self.storage.delete_tool(name)
        else:
            record.status = "error"
            record.updated_at = datetime.now().isoformat()
            self.storage.upsert_tool(record)
        return self._operation_result(
            success=success,
            status="removed" if success else "error",
            message=result,
            error_code="tool_uninstall_failed" if not success else None,
        )

    def list_tools(self) -> list[dict[str, Any]]:
        tools = self.storage.load_tools()
        return [record.to_dict() for record in tools.values()]

    def get_tool_status(self, name: str) -> dict[str, Any]:
        record = self.storage.get_tool(name)
        if record is None:
            return self._not_found_result("tool", name)
        return self._operation_result(
            success=True,
            status=record.status,
            message=f"Tool '{name}' status retrieved",
            data=record.to_dict(),
            tool=record.to_dict(),
        )

    def list_objects(self) -> list[dict[str, Any]]:
        objects = self.storage.load_objects()
        return [
            self._refresh_object_record(record).to_dict() for record in objects.values()
        ]

    def get_object_status(self, name: str) -> dict[str, Any]:
        record = self.storage.get_object(name)
        if record is None:
            return self._not_found_result("object", name)
        record = self._refresh_object_record(record)
        object_payload = self._build_object_status_payload(record)
        return self._operation_result(
            success=True,
            status=record.status,
            message=f"Object '{name}' status retrieved",
            data=object_payload,
            object=object_payload,
        )

    def clear_object(self, name: str) -> dict[str, Any]:
        record = self.storage.get_object(name)
        if record is None:
            return self._not_found_result("object", name)
        if not is_clearable_object_status(record.status):
            return self._operation_result(
                success=False,
                status="invalid_state",
                message=(
                    f"Object '{name}' is in state '{record.status}' and cannot be "
                    "cleared; use reset or uninstall instead"
                ),
                data=self._build_object_status_payload(record),
                object=self._build_object_status_payload(record),
                error="object_state_not_clearable",
                error_code="object_state_not_clearable",
            )

        previous_status = record.status
        if previous_status == OBJECT_STATUS_INSTALL_FAILED_PRESERVED:
            cleanup = self._cleanup_preserved_object_state(
                record,
                remove_installation=True,
            )
            if not cleanup["success"]:
                return self._operation_result(
                    success=False,
                    status="error",
                    message=cleanup["message"],
                    data=record.to_dict(),
                    object=record.to_dict(),
                    error=cleanup["message"],
                    error_code="object_clear_failed",
                )
            self.storage.delete_object(name)
            payload = {
                "name": name,
                "previous_status": previous_status,
                "status": "removed",
                "cleanup": cleanup["details"],
            }
            return self._operation_result(
                success=True,
                status="removed",
                message=f"✓ Cleared preserved install failure for object '{name}'",
                data=payload,
                object=payload,
            )

        cleanup = self._cleanup_preserved_object_state(
            record,
            remove_installation=False,
        )
        if not cleanup["success"]:
            return self._operation_result(
                success=False,
                status="error",
                message=cleanup["message"],
                data=record.to_dict(),
                object=record.to_dict(),
                error=cleanup["message"],
                error_code="object_clear_failed",
            )
        record.status = OBJECT_STATUS_INSTALLED
        record.installed = True
        record.updated_at = datetime.now().isoformat()
        metadata = record.metadata.copy()
        metadata.pop("connectivity_check", None)
        metadata.pop("failure_state", None)
        metadata["last_clear"] = {
            "previous_status": previous_status,
            "cleared_at": record.updated_at,
            "cleanup": cleanup["details"],
        }
        record.metadata = metadata
        self.storage.upsert_object(record)
        object_payload = self._build_object_status_payload(record)
        return self._operation_result(
            success=True,
            status=record.status,
            message=f"✓ Cleared preserved start failure for object '{name}'",
            data=object_payload,
            object=object_payload,
        )

    def reset_object(self, name: str) -> dict[str, Any]:
        record = self.storage.get_object(name)
        if record is None:
            return self._not_found_result("object", name)
        if not is_resettable_object_status(record.status):
            return self._operation_result(
                success=False,
                status="invalid_state",
                message=(
                    f"Object '{name}' is in state '{record.status}' and cannot be reset"
                ),
                data=self._build_object_status_payload(record),
                object=self._build_object_status_payload(record),
                error="object_state_not_resettable",
                error_code="object_state_not_resettable",
            )

        previous_status = record.status
        if previous_status == OBJECT_STATUS_INSTALL_FAILED_PRESERVED:
            cleanup = self._cleanup_preserved_object_state(
                record,
                remove_installation=True,
            )
            if not cleanup["success"]:
                return self._operation_result(
                    success=False,
                    status="error",
                    message=cleanup["message"],
                    data=record.to_dict(),
                    object=record.to_dict(),
                    error=cleanup["message"],
                    error_code="object_reset_failed",
                )
            self.storage.delete_object(name)
            payload = {
                "name": name,
                "previous_status": previous_status,
                "status": "removed",
                "cleanup": cleanup["details"],
            }
            return self._operation_result(
                success=True,
                status="removed",
                message=f"✓ Reset object '{name}' to initial state",
                data=payload,
                object=payload,
            )

        uninstall_result = self.uninstall_object(name)
        if not uninstall_result.get("success"):
            uninstall_result["error_code"] = "object_reset_failed"
            return uninstall_result

        payload = {
            "name": name,
            "previous_status": previous_status,
            "status": "removed",
        }
        return self._operation_result(
            success=True,
            status="removed",
            message=f"✓ Reset object '{name}' to initial state",
            data=payload,
            object=payload,
            checks=uninstall_result.get("checks"),
        )

    def add_case(self, case_id: str, case_data: dict[str, Any]) -> dict[str, Any]:
        case_manager = CaseManager(self._bootstrap_environment())
        message = case_manager.add_case(case_id, case_data)
        success = message.startswith("✓")
        return self._operation_result(
            success=success,
            status="created" if success else "error",
            message=message,
            data={"case_id": case_id},
            case_id=case_id,
            error_code="case_create_failed" if not success else None,
        )

    def get_case(self, case_id: str) -> dict[str, Any] | None:
        case_manager = CaseManager(self._bootstrap_environment())
        return case_manager.get_case(case_id)

    def list_cases(self) -> list[dict[str, Any]]:
        case_manager = CaseManager(self._bootstrap_environment())
        return list(case_manager.cases.values())

    def delete_case(self, case_id: str) -> dict[str, Any]:
        case_manager = CaseManager(self._bootstrap_environment())
        deleted = case_manager.delete_case(case_id)
        if not deleted:
            return self._not_found_result("case", case_id)
        return self._operation_result(
            success=True,
            status="removed",
            message=f"✓ Test case '{case_id}' removed",
            data={"case_id": case_id},
            case_id=case_id,
        )

    def create_suite(self, suite_data: dict[str, Any]) -> dict[str, Any]:
        suite_manager = self._get_suite_manager()
        suite = suite_manager.create_suite(suite_data)
        return self._operation_result(
            success=True,
            status="created",
            message=f"Suite '{suite.name}' created",
            data=suite.to_dict(),
            suite=suite.to_dict(),
        )

    def generate_data(
        self,
        data_type: str,
        *,
        count: int = 1,
        locale: str = "zh_CN",
        format_type: str = "json",
        table: str | None = None,
        dialect: str = "generic",
        batch_size: int = 100,
        seed: int | None = None,
    ) -> dict[str, Any]:
        try:
            generator = DataGenerator(DataGenerationConfig(locale=locale, seed=seed))
            if format_type == "sql":
                if not table:
                    return self._operation_result(
                        success=False,
                        status="invalid",
                        message="Table name is required for SQL format",
                        error="table_required",
                        error_code="data_table_required",
                    )
                result = generator.generate_sql(
                    data_type=data_type,
                    count=count,
                    table=table,
                    dialect=dialect,
                    batch_size=batch_size,
                )
            else:
                result = generator.generate(
                    data_type=data_type,
                    count=count,
                    format=format_type,
                )
        except Exception as exc:
            return self._operation_result(
                success=False,
                status="error",
                message=f"Failed to generate data of type '{data_type}'",
                error=str(exc),
                error_code="data_generation_failed",
            )

        return self._operation_result(
            success=True,
            status="generated",
            message=f"Generated {count} item(s) of type '{data_type}'",
            data={"result": result, "format": format_type, "count": count},
        )

    def save_data_template(
        self,
        name: str,
        definition: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            template_manager = self._get_data_template_manager()
            template_manager.save_template(name, definition)
            return self._operation_result(
                success=True,
                status="saved",
                message=f"Template '{name}' saved",
                data={"name": name, "definition": definition},
            )
        except Exception as exc:
            return self._operation_result(
                success=False,
                status="error",
                message=f"Failed to save template '{name}'",
                error=str(exc),
                error_code="template_save_failed",
            )

    def list_data_templates(self) -> dict[str, Any]:
        templates = self._get_data_template_manager().list_templates()
        return self._operation_result(
            success=True,
            status="ok",
            message=f"Retrieved {len(templates)} data templates",
            data=templates,
        )

    def generate_data_from_template(
        self,
        name: str,
        *,
        count: int = 1,
    ) -> dict[str, Any]:
        template_manager = self._get_data_template_manager()
        template = template_manager.load_template(name)
        if template is None:
            return self._not_found_result("template", name)
        try:
            generator = DataGenerator(DataGenerationConfig())
            results = generator.generate_from_template(template, count=count)
        except Exception as exc:
            return self._operation_result(
                success=False,
                status="error",
                message=f"Failed to generate data from template '{name}'",
                error=str(exc),
                error_code="template_generate_failed",
            )
        return self._operation_result(
            success=True,
            status="generated",
            message=f"Generated {count} item(s) from template '{name}'",
            data={"name": name, "results": results},
        )

    def import_contract(
        self,
        source: str | Path,
        name: str | None = None,
    ) -> dict[str, Any]:
        try:
            contract = self._get_contract_manager().import_contract(source, name)
        except Exception as exc:
            error_text = str(exc)
            error_code = (
                "contract_import_dependency_missing"
                if "prance" in error_text.lower()
                else "contract_import_failed"
            )
            return self._operation_result(
                success=False,
                status="error",
                message=f"Failed to import contract from '{source}'",
                error=error_text,
                error_code=error_code,
            )
        return self._operation_result(
            success=True,
            status="imported",
            message=f"Contract '{contract.name}' imported",
            data=contract.to_dict(),
            contract=contract.to_dict(),
        )

    def list_contracts(self) -> dict[str, Any]:
        contracts = self._get_contract_manager().list_contracts()
        return self._operation_result(
            success=True,
            status="ok",
            message=f"Retrieved {len(contracts)} contracts",
            data=contracts,
        )

    def get_contract(
        self,
        name: str,
    ) -> dict[str, Any]:
        contract = self._get_contract_manager().load_contract(name)
        if contract is None:
            return self._not_found_result("contract", name)
        return self._operation_result(
            success=True,
            status="ok",
            message=f"Contract '{name}' loaded",
            data=contract.to_dict(),
            contract=contract.to_dict(),
        )

    def delete_contract(self, name: str) -> dict[str, Any]:
        deleted = self._get_contract_manager().delete_contract(name)
        if not deleted:
            return self._not_found_result("contract", name)
        return self._operation_result(
            success=True,
            status="removed",
            message=f"Contract '{name}' deleted",
            data={"name": name},
        )

    def generate_cases_from_contract(
        self,
        name: str,
        *,
        persist: bool = True,
    ) -> dict[str, Any]:
        manager = self._get_contract_manager()
        cases = manager.generate_test_cases(name)
        if not cases:
            return self._operation_result(
                success=False,
                status="empty",
                message=f"No cases generated from contract '{name}'",
                error="contract_cases_empty",
                error_code="contract_cases_empty",
            )

        persisted_ids: list[str] = []
        if persist:
            case_manager = CaseManager(self._bootstrap_environment())
            for case in cases:
                case_id = case["id"]
                case_manager.add_case(case_id, case)
                persisted_ids.append(case_id)

        return self._operation_result(
            success=True,
            status="generated",
            message=f"Generated {len(cases)} case(s) from contract '{name}'",
            data={"cases": cases, "persisted_case_ids": persisted_ids},
        )

    def validate_contract_response(
        self,
        name: str,
        endpoint: str,
        method: str,
        status_code: int,
        response_body: dict[str, Any],
    ) -> dict[str, Any]:
        passed, errors = self._get_contract_manager().validate_response(
            name,
            endpoint,
            method,
            status_code,
            response_body,
        )
        return self._operation_result(
            success=passed,
            status="valid" if passed else "invalid",
            message="Contract response validation passed"
            if passed
            else "Contract response validation failed",
            data={"errors": errors},
            error=errors if errors else None,
            error_code="contract_validation_failed" if not passed else None,
        )

    def start_mock_server(
        self,
        name: str,
        *,
        port: int = 8080,
        host: str = "127.0.0.1",
        blocking: bool = False,
    ) -> dict[str, Any]:
        server = self._mock_servers.get(name)
        if server is None:
            config_path = self._mock_config_path(name)
            if config_path.exists():
                server = MockServer.load_config(config_path)
            else:
                server = MockServer(MockConfig(name=name, port=port, host=host))
            self._mock_servers[name] = server

        if server.is_running():
            self._save_mock_state(name, {"status": "running", "blocking": blocking})
            return self._operation_result(
                success=True,
                status="running",
                message=f"Mock server '{name}' is already running",
                data=self._mock_status_payload(name, server),
            )

        try:
            server.start(blocking=blocking)
            server.save_config(self._mock_config_path(name))
            self._save_mock_state(
                name,
                {
                    "status": "running",
                    "blocking": blocking,
                    "last_started_at": datetime.now().isoformat(),
                },
            )
        except Exception as exc:
            self._save_mock_state(
                name,
                {
                    "status": "error",
                    "blocking": blocking,
                    "last_error": str(exc),
                    "updated_at": datetime.now().isoformat(),
                },
            )
            return self._operation_result(
                success=False,
                status="error",
                message=f"Failed to start mock server '{name}'",
                error=str(exc),
                error_code="mock_start_failed",
            )
        return self._operation_result(
            success=True,
            status="running",
            message=f"Mock server '{name}' started",
            data=self._mock_status_payload(name, server),
        )

    def stop_mock_server(self, name: str) -> dict[str, Any]:
        server = self._mock_servers.get(name)
        if server is None:
            config_path = self._mock_config_path(name)
            if not config_path.exists():
                return self._not_found_result("mock", name)
            server = MockServer.load_config(config_path)
            state = self._load_mock_state(name)
            server._running = state.get("status") == "running"  # noqa: SLF001
            self._mock_servers[name] = server

        try:
            server.stop()
            server.save_config(self._mock_config_path(name))
            self._save_mock_state(
                name,
                {
                    "status": "stopped",
                    "last_stopped_at": datetime.now().isoformat(),
                },
            )
        except Exception as exc:
            self._save_mock_state(
                name,
                {
                    "status": "error",
                    "last_error": str(exc),
                    "updated_at": datetime.now().isoformat(),
                },
            )
            return self._operation_result(
                success=False,
                status="error",
                message=f"Failed to stop mock server '{name}'",
                error=str(exc),
                error_code="mock_stop_failed",
            )
        return self._operation_result(
            success=True,
            status="stopped",
            message=f"Mock server '{name}' stopped",
            data=self._mock_status_payload(name, server),
        )

    def get_mock_server_status(self, name: str) -> dict[str, Any]:
        server = self._mock_servers.get(name)
        if server is None:
            config_path = self._mock_config_path(name)
            if not config_path.exists():
                return self._not_found_result("mock", name)
            server = MockServer.load_config(config_path)
            self._mock_servers[name] = server
        data = self._mock_status_payload(name, server)
        return self._operation_result(
            success=True,
            status=data["status"],
            message=f"Mock server '{name}' status retrieved",
            data=data,
        )

    def list_mock_servers(self) -> dict[str, Any]:
        names = {path.stem for path in self._mock_dir().glob("*.json")}
        names.update(self._mock_servers.keys())
        servers = []
        for name in sorted(names):
            server = self._mock_servers.get(name)
            if server is None:
                server = MockServer.load_config(self._mock_config_path(name))
                self._mock_servers[name] = server
            servers.append(self._mock_status_payload(name, server))
        return self._operation_result(
            success=True,
            status="ok",
            message=f"Retrieved {len(servers)} mock server(s)",
            data=servers,
        )

    def add_mock_route(
        self,
        name: str,
        path: str,
        method: str,
        response: dict[str, Any],
        when: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        server = self._mock_servers.get(name)
        if server is None:
            config_path = self._mock_config_path(name)
            if not config_path.exists():
                return self._not_found_result("mock", name)
            server = MockServer.load_config(config_path)
            self._mock_servers[name] = server
        route_id = server.add_route(path, method, response, when)
        server.save_config(self._mock_config_path(name))
        payload = self._mock_status_payload(name, server)
        return self._operation_result(
            success=True,
            status="updated",
            message=f"Route added to mock server '{name}'",
            data={
                "route_id": route_id,
                "config": server.config.to_dict(),
                "mock": payload,
            },
        )

    def get_mock_logs(self, name: str, *, limit: int = 10) -> dict[str, Any]:
        server = self._mock_servers.get(name)
        if server is None:
            config_path = self._mock_config_path(name)
            if not config_path.exists():
                return self._not_found_result("mock", name)
            server = MockServer.load_config(config_path)
            self._mock_servers[name] = server
        history = [item.to_dict() for item in server.get_request_history()[-limit:]]
        state = self._load_mock_state(name)
        persisted = bool(history)
        return self._operation_result(
            success=True,
            status="ok",
            message=f"Retrieved {len(history)} request log(s) for mock server '{name}'",
            data={
                "requests": history,
                "persisted": persisted,
                "runtime_state": state.get("status", "unknown"),
            },
        )

    def list_suites(self) -> list[str]:
        suite_manager = self._get_suite_manager()
        return suite_manager.list_suites()

    def get_suite(self, name: str) -> dict[str, Any] | None:
        suite_manager = self._get_suite_manager()
        suite = suite_manager.load_suite(name)
        return suite.to_dict() if suite else None

    def delete_suite(self, name: str) -> dict[str, Any]:
        suite_manager = self._get_suite_manager()
        success = suite_manager.delete_suite(name)
        if not success:
            return self._not_found_result("suite", name)
        return self._operation_result(
            success=True,
            status="removed",
            message=f"Suite '{name}' deleted",
            data={"name": name},
        )

    def validate_suite(self, name: str) -> dict[str, Any]:
        suite_manager = self._get_suite_manager()
        suite = suite_manager.load_suite(name)
        if suite is None:
            return self._not_found_result("suite", name)
        valid, errors = suite.validate()
        return self._operation_result(
            success=valid,
            status="valid" if valid else "invalid",
            message=f"Suite '{name}' validation passed"
            if valid
            else f"Suite '{name}' validation failed",
            data=suite.to_dict(),
            suite=suite.to_dict(),
            errors=errors,
            error=errors if errors else None,
            error_code="suite_validation_failed" if not valid else None,
        )

    def run_suite(
        self,
        name: str,
        parallel: bool = False,
        workers: int = 4,
        stop_on_failure: bool = False,
        timeout: int = 0,
        retry_count: int = 0,
    ) -> dict[str, Any]:
        env_manager = self._bootstrap_environment()
        case_manager = CaseManager(env_manager)
        suite_manager = self._get_suite_manager()
        before_snapshots: dict[str, dict[str, Any] | None] = {}

        def _capture_before_snapshot(case_id: str) -> None:
            case_def = case_manager.get_case(case_id)
            before_snapshots[case_id] = (
                self._capture_data_state_snapshot(case_def, phase="before")
                if case_def
                else None
            )

        result = suite_manager.execute_suite(
            suite_name=name,
            case_manager=case_manager,
            parallel=parallel,
            max_workers=workers,
            stop_on_failure=stop_on_failure,
            timeout=timeout,
            retry_count=retry_count,
            before_case_callback=_capture_before_snapshot,
        )
        for case_id, case_result in case_manager.results.items():
            self._persist_execution(
                case_id,
                case_result,
                case_manager,
                data_state_snapshot_before=before_snapshots.get(case_id),
            )
        if "results" in result:
            result["results"] = [
                self._normalize_suite_result(item) for item in result["results"]
            ]
        result.setdefault(
            "message",
            f"Suite '{name}' run completed: {result.get('passed', 0)} passed, "
            f"{result.get('failed', 0)} failed",
        )
        result.setdefault("workspace", str(self.root_path))
        result.setdefault(
            "error", None if result.get("success") else result.get("results")
        )
        return result

    def run_case(
        self, case_id: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        case_manager = CaseManager(self._bootstrap_environment())
        (
            result,
            case_definition,
            crash_snapshot_before,
            object_artifacts_before,
            data_state_snapshot_before,
        ) = self._execute_case_with_artifact_capture(
            case_manager,
            case_id,
            params=params,
        )
        self._persist_execution(
            case_id,
            result,
            case_manager,
            case_definition_override=case_definition,
            crash_snapshot_before=crash_snapshot_before,
            object_artifacts_before=object_artifacts_before,
            data_state_snapshot_before=data_state_snapshot_before,
        )
        payload = self._result_payload(result)
        payload["message"] = (
            f"Case '{case_id}' completed with status '{payload['status']}'"
        )
        payload["workspace"] = str(self.root_path)
        return payload

    def run_all_cases(
        self,
        filter_text: str | None = None,
        parallel: bool = False,
        workers: int = 4,
        timeout: int = 0,
    ) -> dict[str, Any]:
        from ..execution import ExecutionTask, ParallelExecutor, SequentialExecutor

        case_manager = CaseManager(self._bootstrap_environment())
        case_ids = list(case_manager.cases.keys())
        if filter_text:
            case_ids = [case_id for case_id in case_ids if filter_text in case_id]

        if not case_ids:
            return {
                "success": True,
                "status": "empty",
                "message": "No matching cases to run",
                "total": 0,
                "passed": 0,
                "failed": 0,
                "results": [],
                "workspace": str(self.root_path),
                "error": None,
            }

        if parallel:
            executor = ParallelExecutor(max_workers=workers)
            tasks = [
                ExecutionTask(
                    task_id=case_id,
                    func=(
                        lambda case_id=case_id: (
                            self._execute_case_with_artifact_capture(
                                case_manager,
                                case_id,
                            )
                        )
                    ),
                    timeout=float(timeout or 300),
                )
                for case_id in case_ids
            ]
            execution_results = executor.execute(tasks)
            executor.shutdown()
            results: list[dict[str, Any]] = []
            for execution_result in execution_results:
                case_result = execution_result.result
                case_definition = None
                crash_snapshot_before = None
                object_artifacts_before = None
                data_state_snapshot_before = None
                if isinstance(case_result, tuple) and len(case_result) >= 4:
                    raw_tuple = case_result
                    (
                        case_result,
                        case_definition,
                        crash_snapshot_before,
                        object_artifacts_before,
                    ) = raw_tuple[:4]
                    if len(raw_tuple) > 4:
                        data_state_snapshot_before = raw_tuple[4]
                if isinstance(case_result, TestCaseResult):
                    self._persist_execution(
                        case_result.case_id,
                        case_result,
                        case_manager,
                        case_definition_override=case_definition,
                        crash_snapshot_before=crash_snapshot_before,
                        object_artifacts_before=object_artifacts_before,
                        data_state_snapshot_before=data_state_snapshot_before,
                    )
                    results.append(self._result_payload(case_result))
            return self._summarize_results(results)

        seq_executor = SequentialExecutor(
            stop_on_failure=False,
            timeout=float(timeout or 300),
        )
        tasks = [
            ExecutionTask(
                task_id=case_id,
                func=(
                    lambda case_id=case_id: self._execute_case_with_artifact_capture(
                        case_manager,
                        case_id,
                    )
                ),
            )
            for case_id in case_ids
        ]
        execution_results = seq_executor.execute(tasks)
        results = []
        for execution_result in execution_results:
            case_result = execution_result.result
            case_definition = None
            crash_snapshot_before = None
            object_artifacts_before = None
            data_state_snapshot_before = None
            if isinstance(case_result, tuple) and len(case_result) >= 4:
                raw_tuple = case_result
                (
                    case_result,
                    case_definition,
                    crash_snapshot_before,
                    object_artifacts_before,
                ) = raw_tuple[:4]
                if len(raw_tuple) > 4:
                    data_state_snapshot_before = raw_tuple[4]
            if isinstance(case_result, TestCaseResult):
                self._persist_execution(
                    case_result.case_id,
                    case_result,
                    case_manager,
                    case_definition_override=case_definition,
                    crash_snapshot_before=crash_snapshot_before,
                    object_artifacts_before=object_artifacts_before,
                    data_state_snapshot_before=data_state_snapshot_before,
                )
                results.append(self._result_payload(case_result))
        return self._summarize_results(results)

    def generate_report(
        self,
        format_type: str = "html",
        output_path: str | Path | None = None,
    ) -> str:
        env_manager = self._bootstrap_environment()
        case_manager = CaseManager(env_manager)
        latest_results = self.storage.latest_executions_by_case()

        case_manager.results = {}
        case_manager.passed_cases = []
        case_manager.failed_cases = []
        for case_id, record in latest_results.items():
            result = self._execution_to_result(record)
            case_manager.results[case_id] = result
            if result.status == "passed":
                case_manager.passed_cases.append(case_id)
            else:
                case_manager.failed_cases.append(case_id)

        report_generator = ReportGenerator(env_manager, case_manager)
        report_path = Path(output_path) if output_path else None
        return report_generator.generate_report(format_type, report_path)

    def list_execution_records(
        self,
        case_id: str | None = None,
    ) -> list[dict[str, Any]]:
        records = self.storage.list_executions()
        if case_id is not None:
            records = [record for record in records if record.case_id == case_id]
        return [record.to_dict() for record in records]

    def get_execution_record(self, execution_id: str) -> dict[str, Any]:
        record = self.storage.get_execution(execution_id)
        if record is None:
            return self._not_found_result("execution", execution_id)
        return self._operation_result(
            success=True,
            status="ok",
            message=f"Execution '{execution_id}' retrieved",
            data=record.to_dict(),
            execution=record.to_dict(),
        )

    def get_execution_artifacts(
        self,
        execution_id: str,
        *,
        include_contents: bool = False,
    ) -> dict[str, Any]:
        artifact_index = self.storage.get_execution_artifact_index(execution_id)
        if artifact_index is None:
            return self._not_found_result("execution_artifacts", execution_id)

        log_index = self.storage.get_execution_log_index(execution_id)
        artifact_index.setdefault("indexes", {})
        artifact_index["indexes"]["log_index"] = artifact_index["indexes"].get(
            "log_index",
            str(self.storage.artifacts_dir / execution_id / "logs" / "log_index.json"),
        )
        artifact_index["log_index"] = log_index or {}
        artifact_index["object_artifacts_summary"] = (
            self._build_execution_object_artifacts_summary(artifact_index)
        )
        artifact_index["problem_summary"] = self._build_execution_problem_summary(
            execution_id
        )

        if include_contents:
            contents: dict[str, Any] = {}
            for artifact_name, relative_path in artifact_index.get("files", {}).items():
                contents[artifact_name] = self.storage.read_artifact_file(relative_path)
            artifact_index["contents"] = contents

        return self._operation_result(
            success=True,
            status="ok",
            message=f"Artifacts for execution '{execution_id}' retrieved",
            data=artifact_index,
            artifacts=artifact_index,
        )

    @staticmethod
    def _matches_problem_filters(
        record: ProblemRecord,
        *,
        object_name: str | None = None,
        environment_id: str | None = None,
        status: str | None = None,
        preservation_status: str | None = None,
        can_replay: Literal[True] | None = None,
        can_recover: Literal[True] | None = None,
    ) -> bool:
        if object_name is not None and object_name not in record.object_refs:
            return False
        if environment_id is not None and record.environment_id != environment_id:
            return False
        if status is not None and record.status != status:
            return False
        if (
            preservation_status is not None
            and record.preservation_status != preservation_status
        ):
            return False
        metadata = record.metadata if isinstance(record.metadata, dict) else {}
        capabilities = metadata.get("capabilities", {})
        if not isinstance(capabilities, dict):
            capabilities = {}
        if can_replay is True and capabilities.get("can_replay") is not True:
            return False
        if can_recover is True and capabilities.get("can_recover") is not True:
            return False
        return True

    def list_problem_records(
        self,
        *,
        problem_type: str | None = None,
        case_id: str | None = None,
        execution_id: str | None = None,
        object_name: str | None = None,
        environment_id: str | None = None,
        status: str | None = None,
        preservation_status: str | None = None,
        can_replay: Literal[True] | None = None,
        can_recover: Literal[True] | None = None,
        include_assets_summary: bool = False,
    ) -> list[dict[str, Any]]:
        records = self._list_problem_record_models(
            case_id=case_id,
            execution_id=execution_id,
        )
        filtered = []
        for record in records:
            if problem_type is not None and record.problem_type != problem_type:
                continue
            if case_id is not None and record.case_id != case_id:
                continue
            if execution_id is not None and record.execution_id != execution_id:
                continue
            if not self._matches_problem_filters(
                record,
                object_name=object_name,
                environment_id=environment_id,
                status=status,
                preservation_status=preservation_status,
                can_replay=can_replay,
                can_recover=can_recover,
            ):
                continue
            payload = self._problem_record_payload(record)
            if include_assets_summary:
                payload["assets_summary"] = self._build_problem_asset_summary(record)
            filtered.append(payload)
        return sorted(filtered, key=lambda item: item["created_at"], reverse=True)

    def get_problem_assets(self, problem_id: str) -> dict[str, Any]:
        assets = self.storage.get_problem_assets(problem_id)
        if assets is None:
            return self._not_found_result("problem_assets", problem_id)
        payload = self._problem_assets_payload(assets)
        record = self.storage.get_problem_record(problem_id)
        if record is not None:
            payload["verification_summary"] = self._build_problem_verification_summary(
                record, assets
            )
        return self._operation_result(
            success=True,
            status="ok",
            message=f"Assets for problem '{problem_id}' retrieved",
            data=payload,
            assets=payload,
        )

    def list_problem_recovery_history(self, problem_id: str) -> dict[str, Any]:
        record = self.storage.get_problem_record(problem_id)
        if record is None:
            return self._not_found_result("problem", problem_id)
        history_records = self.storage.list_problem_recovery_history(problem_id)
        actions = [r.to_dict() for r in history_records]
        if not actions:
            fallback = self.storage.get_problem_recovery(problem_id)
            if fallback is not None:
                actions = [fallback.to_dict()]
        latest_action = actions[0]["status"] if actions else None
        latest_action_type = actions[0].get("action_type") if actions else None
        latest = f"{latest_action_type}:{latest_action}" if latest_action_type else None
        verification_runs = [
            self._build_verification_run_from_action(a) for a in actions
        ]
        verification_summary = self._build_history_verification_summary(
            verification_runs
        )
        payload = {
            "problem_id": problem_id,
            "count": len(actions),
            "latest_action": latest,
            "actions": actions,
            "verification_runs": verification_runs,
            "verification_summary": verification_summary,
        }
        return self._operation_result(
            success=True,
            status="ok",
            message=f"Recovery history for problem '{problem_id}' retrieved",
            data=payload,
            history=payload,
        )

    def update_problem_record(
        self,
        problem_id: str,
        *,
        status: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        if status is None and notes is None:
            return self._operation_result(
                success=False,
                status="invalid",
                message="At least one of 'status' or 'notes' must be provided",
                error="problem_update_empty",
                error_code="problem_update_empty",
            )
        if status is not None and status not in PROBLEM_ALLOWED_STATUSES:
            return self._operation_result(
                success=False,
                status="invalid",
                message=(
                    f"Invalid problem status '{status}'. "
                    f"Allowed: {', '.join(sorted(PROBLEM_ALLOWED_STATUSES))}"
                ),
                error="problem_status_invalid",
                error_code="problem_status_invalid",
            )
        record = self.storage.get_problem_record(problem_id)
        if record is None:
            return self._not_found_result("problem", problem_id)
        now = datetime.now().isoformat()
        if status is not None:
            record.status = status
            record.latest_action = f"status:{status}"
        if notes is not None:
            record.notes = notes
            if status is None:
                record.latest_action = "note:updated"
        record.updated_at = now
        self.storage.save_problem_record(record)
        assets = self.storage.get_problem_assets(problem_id)
        if assets is not None:
            if status is not None:
                assets.status = status
            assets.updated_at = now
            self.storage.save_problem_assets(assets)
        payload = self._problem_record_payload(record)
        return self._operation_result(
            success=True,
            status="ok",
            message=f"Problem '{problem_id}' updated",
            data=payload,
            problem=payload,
        )

    def _problem_record_payload(self, record: ProblemRecord) -> dict[str, Any]:
        payload = record.to_dict()
        metadata = payload.get("metadata", {})
        preservation = metadata.get("preservation", {})
        capabilities = metadata.get("capabilities", {})
        if isinstance(preservation, dict):
            payload["preservation"] = preservation
        if isinstance(capabilities, dict):
            payload["capabilities"] = capabilities
        latest_comparison = self._extract_problem_latest_comparison(payload)
        payload["investigation"] = self._build_problem_investigation_summary(
            payload,
            view="problem",
            comparison=latest_comparison
            if isinstance(latest_comparison, dict)
            else None,
        )
        return payload

    def _build_problem_asset_summary(
        self,
        record: ProblemRecord,
        assets: ProblemAssetRecord | None = None,
    ) -> dict[str, Any]:
        load_error: str | None = None
        if assets is None:
            try:
                assets = self.storage.get_problem_assets(record.problem_id)
            except (json.JSONDecodeError, OSError, ValueError) as exc:
                load_error = str(exc)
        assets_available = assets is not None
        available_assets: list[str] = []
        missing_assets: list[str] = []
        details: dict[str, Any] = {}
        diagnostics_status: str = "unavailable"
        if assets is not None:
            details = assets.details if isinstance(assets.details, dict) else {}
            preservation = details.get("preservation", {})
            if isinstance(preservation, dict):
                available_assets = list(preservation.get("available_assets", []))
                missing_assets = list(preservation.get("missing_assets", []))
            runtime_backend = (
                assets.metadata.get("runtime_backend", {})
                if isinstance(assets.metadata, dict)
                else {}
            )
            object_artifacts = details.get("object_artifacts", {})
            if runtime_backend and object_artifacts:
                diagnostics_status = "complete"
            elif runtime_backend or object_artifacts:
                diagnostics_status = "partial"
            else:
                diagnostics_status = "unavailable"
        verification_summary = self._build_problem_verification_summary(record, assets)
        result: dict[str, Any] = {
            "problem_id": record.problem_id,
            "problem_type": record.problem_type,
            "status": record.status,
            "created_at": record.created_at,
            "preservation_status": record.preservation_status,
            "execution_id": record.execution_id or None,
            "case_id": record.case_id or None,
            "environment_id": record.environment_id or None,
            "object_refs": list(record.object_refs),
            "assets_available": assets_available,
            "available_assets": available_assets,
            "missing_assets": missing_assets,
            "artifact_refs": list(record.artifact_refs.keys())
            if isinstance(record.artifact_refs, dict)
            else [],
            "diagnostics_status": diagnostics_status,
            "verification_summary": verification_summary,
            "suggested_views": self._build_diagnostic_next_views(
                problem_id=record.problem_id,
                execution_id=record.execution_id,
                object_refs=record.object_refs,
            ),
        }
        if load_error:
            result["error"] = load_error
        return result

    def _build_problem_collection_summary(
        self,
        problem_summaries: list[dict[str, Any]],
    ) -> dict[str, Any]:
        by_type: dict[str, int] = {}
        by_status: dict[str, int] = {}
        for summary in problem_summaries:
            ptype = summary.get("problem_type", "unknown")
            pstatus = summary.get("status", "unknown")
            by_type[ptype] = by_type.get(ptype, 0) + 1
            by_status[pstatus] = by_status.get(pstatus, 0) + 1
        sorted_summaries = sorted(
            problem_summaries,
            key=lambda p: (p.get("created_at") is None, p.get("created_at", "")),
            reverse=True,
        )
        recent = sorted_summaries[:10]
        suggested_views: list[dict[str, str]] = []
        if problem_summaries:
            suggested_views.append(
                {
                    "view": "problem_list",
                    "command": "ptest problem list",
                    "reason": "list all problems with filters",
                }
            )
            first_id = recent[0]["problem_id"] if recent else ""
            if first_id:
                suggested_views.append(
                    {
                        "view": "problem_assets",
                        "command": f"ptest problem assets {first_id}",
                        "reason": "inspect preserved problem assets for most recent problem",
                    }
                )
        return {
            "total_count": len(problem_summaries),
            "by_type": by_type,
            "by_status": by_status,
            "recent_problems": recent,
            "suggested_views": suggested_views,
        }

    def _build_execution_problem_summary(
        self,
        execution_id: str,
    ) -> dict[str, Any]:
        try:
            records = self.storage.list_problem_records_for_execution(execution_id)
        except (json.JSONDecodeError, OSError, ValueError):
            return {
                "total_count": 0,
                "by_type": {},
                "by_status": {},
                "recent_problems": [],
                "suggested_views": [],
            }
        summaries = [self._build_problem_asset_summary(record) for record in records]
        return self._build_problem_collection_summary(summaries)

    def _build_object_problem_summary(
        self,
        object_name: str,
        *,
        limit: int = 10,
    ) -> dict[str, Any]:
        matches: list[ProblemRecord] = []
        for record in self.storage.load_problem_records().values():
            if object_name not in record.object_refs:
                continue
            matches.append(record)
        matches.sort(key=lambda r: r.created_at, reverse=True)
        by_type: dict[str, int] = {}
        by_status: dict[str, int] = {}
        for record in matches:
            by_type[record.problem_type] = by_type.get(record.problem_type, 0) + 1
            by_status[record.status] = by_status.get(record.status, 0) + 1
        summaries = [
            self._build_problem_asset_summary(record) for record in matches[:limit]
        ]
        result = self._build_problem_collection_summary(summaries)
        result["total_count"] = len(matches)
        result["by_type"] = by_type
        result["by_status"] = by_status
        return result

    @staticmethod
    def _build_verification_run_from_action(action: dict[str, Any]) -> dict[str, Any]:
        action_type = action.get("action_type", "unknown")
        action_status = action.get("status", "unknown")
        success = action.get("success", False)
        mode = action.get("mode", "")
        metadata = action.get("metadata", {})
        result_meta: dict[str, Any] = {}
        if isinstance(metadata, dict):
            raw_result = metadata.get("result", {})
            if isinstance(raw_result, dict):
                result_meta = raw_result

        comparison = result_meta.get("comparison", {})
        reproduced: bool | None = None
        comparison_summary: dict[str, Any] = {}
        if isinstance(comparison, dict) and comparison:
            expectation = comparison.get("expectation", {})
            if isinstance(expectation, dict) and expectation:
                raw_reproduced = expectation.get("reproduced")
                if isinstance(raw_reproduced, bool):
                    reproduced = raw_reproduced
            assertion_outcome = comparison.get("assertion_outcome")
            if assertion_outcome:
                comparison_summary["assertion_outcome"] = assertion_outcome
            summary = comparison.get("summary", {})
            if isinstance(summary, dict):
                comparison_summary["summary"] = summary

        if action_type == "replay":
            if success and action_status == "completed":
                if reproduced is True:
                    result_status = "reproduced"
                elif reproduced is False:
                    result_status = "not_reproduced"
                else:
                    result_status = "inconclusive"
            else:
                result_status = "failed"
        elif action_type == "recover":
            if success and action_status in ("completed", "prepared"):
                result_status = "recovered" if mode != "plan_only" else "inconclusive"
            else:
                result_status = "failed"
        else:
            result_status = "inconclusive"

        reason = ""
        if action_type == "replay":
            if result_status == "reproduced":
                reason = "replay confirms the problem is still reproducible"
            elif result_status == "not_reproduced":
                reason = "replay shows the problem no longer reproduces"
            elif result_status == "failed":
                reason = "replay execution failed"
        elif action_type == "recover":
            if result_status == "recovered":
                reason = (
                    "recovery plan prepared"
                    if action_status == "prepared"
                    else "recovery completed successfully"
                )
            elif result_status == "inconclusive":
                reason = "recovery plan prepared but not executed"
            elif result_status == "failed":
                reason = "recovery execution failed"

        return {
            "action_id": action.get("action_id", ""),
            "action_type": action_type,
            "status": action_status,
            "success": success,
            "created_at": action.get("created_at", ""),
            "mode": mode,
            "result_status": result_status,
            "reproduced": reproduced,
            "comparison_summary": comparison_summary,
            "reason": reason,
        }

    def _build_problem_verification_runs(self, problem_id: str) -> list[dict[str, Any]]:
        try:
            actions = self._problem_recovery_history_actions(problem_id)
        except (json.JSONDecodeError, OSError, ValueError):
            return []
        return [self._build_verification_run_from_action(a) for a in actions]

    @staticmethod
    def _build_history_verification_summary(
        runs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        replay_count = sum(1 for r in runs if r["action_type"] == "replay")
        recover_count = sum(1 for r in runs if r["action_type"] == "recover")
        ever_reproduced = any(r["result_status"] == "reproduced" for r in runs)
        inconclusive_count = sum(
            1 for r in runs if r["result_status"] == "inconclusive"
        )
        latest_result_status = runs[0]["result_status"] if runs else None

        latest_reproduced_at: str | None = None
        latest_successful_recover_at: str | None = None
        for run in runs:
            if run["result_status"] == "reproduced" and latest_reproduced_at is None:
                latest_reproduced_at = run["created_at"]
            if (
                run["result_status"] == "recovered"
                and latest_successful_recover_at is None
            ):
                latest_successful_recover_at = run["created_at"]
            if latest_reproduced_at and latest_successful_recover_at:
                break

        return {
            "run_count": len(runs),
            "replay_count": replay_count,
            "recover_count": recover_count,
            "latest_result_status": latest_result_status,
            "ever_reproduced": ever_reproduced,
            "latest_reproduced_at": latest_reproduced_at,
            "latest_successful_recover_at": latest_successful_recover_at,
            "inconclusive_count": inconclusive_count,
        }

    def _problem_assets_payload(self, assets: ProblemAssetRecord) -> dict[str, Any]:
        payload = assets.to_dict()
        metadata = payload.get("metadata", {})
        details = payload.get("details", {})
        preservation = {}
        if isinstance(details, dict):
            raw_preservation = details.get("preservation", {})
            if isinstance(raw_preservation, dict):
                preservation = raw_preservation
        if not preservation and isinstance(metadata, dict):
            raw_preservation = metadata.get("preservation", {})
            if isinstance(raw_preservation, dict):
                preservation = raw_preservation
        capabilities = metadata.get("capabilities", {})
        if isinstance(preservation, dict):
            payload["preservation"] = preservation
        if isinstance(capabilities, dict):
            payload["capabilities"] = capabilities
        runtime_backend = metadata.get("runtime_backend", {})
        if not isinstance(runtime_backend, dict) or not runtime_backend:
            runtime_backend = self._build_problem_runtime_backend_context(
                payload.get("object_refs", [])
            )
        if isinstance(runtime_backend, dict) and runtime_backend:
            payload["runtime_backend"] = runtime_backend
            if isinstance(metadata, dict):
                metadata["runtime_backend"] = runtime_backend
        reproduction_summary = self._build_problem_reproduction_summary(payload)
        if reproduction_summary is not None:
            payload["reproduction_summary"] = reproduction_summary
        latest_comparison = self._extract_problem_latest_comparison(payload)
        payload["investigation"] = self._build_problem_investigation_summary(
            payload,
            view="assets",
            reproduction_summary=(
                reproduction_summary if isinstance(reproduction_summary, dict) else None
            ),
            comparison=latest_comparison
            if isinstance(latest_comparison, dict)
            else None,
        )
        return payload

    def _problem_recovery_history_actions(
        self, problem_id: str
    ) -> list[dict[str, Any]]:
        history_records = self.storage.list_problem_recovery_history(problem_id)
        actions = [r.to_dict() for r in history_records]
        if not actions:
            fallback = self.storage.get_problem_recovery(problem_id)
            if fallback is not None:
                actions = [fallback.to_dict()]
        return actions

    @staticmethod
    def _latest_history_action(
        actions: list[dict[str, Any]], action_type: str | None = None
    ) -> dict[str, Any] | None:
        """Return the first matching action.

        ``actions`` must be sorted by ``created_at`` descending, which
        :meth:`_problem_recovery_history_actions` guarantees via
        ``WorkspaceStorage.list_problem_recovery_history``.
        """
        for action in actions:
            if action_type is None or action.get("action_type") == action_type:
                return action
        return None

    def _build_problem_verification_summary(
        self,
        record: ProblemRecord,
        assets: ProblemAssetRecord | None = None,
    ) -> dict[str, Any]:
        actions = self._problem_recovery_history_actions(record.problem_id)
        last_action = self._latest_history_action(actions)
        latest_replay = self._latest_history_action(actions, "replay")
        latest_recover = self._latest_history_action(actions, "recover")
        replay_section: dict[str, Any] = {"available": latest_replay is not None}
        if latest_replay is not None:
            replay_action_status = latest_replay.get("status", "unknown")
            replay_succeeded = replay_action_status == "completed"
            replay_metadata = latest_replay.get("metadata", {})
            reproduced: bool | None = None
            if isinstance(replay_metadata, dict):
                result = replay_metadata.get("result", {})
                if isinstance(result, dict):
                    comparison = result.get("comparison", {})
                    if isinstance(comparison, dict) and comparison:
                        expectation = comparison.get("expectation", {})
                        if isinstance(expectation, dict) and expectation:
                            raw_reproduced = expectation.get("reproduced")
                            if isinstance(raw_reproduced, bool):
                                reproduced = raw_reproduced
                        replay_section["assessment"] = comparison.get(
                            "assertion_outcome"
                        )
            if not replay_succeeded:
                reproduced = None
            replay_section["reproduced"] = reproduced
            replay_section["action_status"] = replay_action_status
        recover_section: dict[str, Any] = {"available": latest_recover is not None}
        if latest_recover is not None:
            recover_section["status"] = latest_recover.get("status")
            recover_section["mode"] = latest_recover.get("mode")

        verification_runs = [
            self._build_verification_run_from_action(a) for a in actions
        ]
        ever_reproduced = any(
            r["result_status"] == "reproduced" for r in verification_runs
        )
        latest_result_status = (
            verification_runs[0]["result_status"] if verification_runs else None
        )

        can_replay = self._resolve_can_replay(record, assets)
        suggested = self._suggest_next_action(
            record.status,
            actions,
            replay_section,
            can_replay,
            ever_reproduced=ever_reproduced,
            latest_result_status=latest_result_status,
        )
        last_verified_at = last_action.get("created_at") if last_action else None

        latest_successful_replay: dict[str, Any] | None = None
        latest_failed_replay: dict[str, Any] | None = None
        latest_successful_recover: dict[str, Any] | None = None
        for run in verification_runs:
            if run["action_type"] == "replay":
                if (
                    run["result_status"] == "reproduced"
                    and latest_successful_replay is None
                ):
                    latest_successful_replay = run
                if (
                    run["result_status"] == "not_reproduced"
                    and latest_successful_replay is None
                ):
                    latest_successful_replay = run
                if run["result_status"] == "failed" and latest_failed_replay is None:
                    latest_failed_replay = run
            if run["action_type"] == "recover" and run["result_status"] == "recovered":
                if latest_successful_recover is None:
                    latest_successful_recover = run
            if (
                latest_successful_replay
                and latest_failed_replay
                and latest_successful_recover
            ):
                break

        _TREND_MAP = {
            "reproduced": "reproduced",
            "not_reproduced": "not_reproduced",
            "recovered": "recovered",
            "inconclusive": "inconclusive",
            "failed": "inconclusive",
        }
        if not verification_runs:
            trend = "no_history"
        else:
            trend = _TREND_MAP.get(latest_result_status or "", "no_history")

        runs_preview = verification_runs[:5]

        return {
            "status": record.status,
            "latest_action": record.latest_action,
            "has_notes": bool(record.notes),
            "history_count": len(actions),
            "last_verified_at": last_verified_at,
            "last_action": last_action,
            "latest_replay": replay_section,
            "latest_recover": recover_section,
            "suggested_next_action": suggested,
            "trend": trend,
            "latest_result_status": latest_result_status,
            "ever_reproduced": ever_reproduced,
            "latest_successful_replay": latest_successful_replay,
            "latest_failed_replay": latest_failed_replay,
            "latest_successful_recover": latest_successful_recover,
            "verification_runs_preview": runs_preview,
        }

    @staticmethod
    def _resolve_can_replay(
        record: ProblemRecord, assets: ProblemAssetRecord | None
    ) -> bool:
        for source in (record, assets):
            if source is None:
                continue
            metadata = source.metadata
            if isinstance(metadata, dict):
                capabilities = metadata.get("capabilities", {})
                if (
                    isinstance(capabilities, dict)
                    and capabilities.get("can_replay") is True
                ):
                    return True
        return False

    @staticmethod
    def _suggest_next_action(
        status: str,
        actions: list[dict[str, Any]],
        replay_section: dict[str, Any],
        can_replay: bool = False,
        *,
        ever_reproduced: bool = False,
        latest_result_status: str | None = None,
    ) -> dict[str, str]:
        if status in ("resolved", "closed"):
            return {"action": "no_action", "reason": f"problem is already {status}"}
        if not actions:
            return {
                "action": "run_replay_or_recover",
                "reason": "no verification history yet",
            }

        if latest_result_status == "reproduced":
            return {
                "action": "continue_investigation",
                "reason": "latest replay still reproduces the problem",
            }
        if latest_result_status == "not_reproduced":
            if ever_reproduced:
                return {
                    "action": "compare_runs",
                    "reason": "latest replay no longer reproduces but was previously reproduced",
                }
            return {
                "action": "update_status",
                "reason": "latest replay no longer reproduces the preserved failure",
            }
        if latest_result_status == "recovered":
            if can_replay:
                return {
                    "action": "run_replay",
                    "reason": "recovery plan prepared, replay after applying recovery to verify",
                }
            return {
                "action": "inspect_recovery_plan",
                "reason": "recovery plan prepared but problem type does not support replay",
            }
        if latest_result_status == "inconclusive":
            if can_replay:
                return {
                    "action": "run_replay",
                    "reason": "latest verification inconclusive, replay available to clarify",
                }
            has_recover = any(a.get("action_type") == "recover" for a in actions)
            if has_recover:
                return {
                    "action": "inspect_recovery_plan",
                    "reason": "latest verification inconclusive, recovery plan available",
                }
            return {
                "action": "inspect_history",
                "reason": "latest verification produced inconclusive result",
            }
        if latest_result_status == "failed":
            return {
                "action": "inspect_history",
                "reason": "latest verification execution failed",
            }

        if replay_section.get("available"):
            return {
                "action": "inspect_history",
                "reason": "replay exists but result could not be determined",
            }
        return {"action": "inspect_history", "reason": "unable to determine next step"}

    def get_problem_record(self, problem_id: str) -> dict[str, Any]:
        record = self.storage.get_problem_record(problem_id)
        if record is None:
            return self._not_found_result("problem", problem_id)
        payload = self._problem_record_payload(record)
        assets = self.storage.get_problem_assets(problem_id)
        if assets is not None:
            assets_payload = self._problem_assets_payload(assets)
            payload_for_investigation = {
                **payload,
                "details": assets_payload.get("details", {}),
                "recovery": assets_payload.get("recovery", {}),
                "preservation": assets_payload.get(
                    "preservation", payload.get("preservation", {})
                ),
                "capabilities": assets_payload.get(
                    "capabilities", payload.get("capabilities", {})
                ),
                "runtime_backend": assets_payload.get(
                    "runtime_backend", payload.get("runtime_backend", {})
                ),
            }
            payload["investigation"] = self._build_problem_investigation_summary(
                payload_for_investigation,
                view="problem",
                reproduction_summary=assets_payload.get("reproduction_summary")
                if isinstance(assets_payload.get("reproduction_summary"), dict)
                else None,
                comparison=self._extract_problem_latest_comparison(payload),
            )
        payload["verification_summary"] = self._build_problem_verification_summary(
            record, assets
        )
        return self._operation_result(
            success=True,
            status="ok",
            message=f"Problem '{problem_id}' retrieved",
            data=payload,
            problem=payload,
        )

    def get_problem_recovery(self, problem_id: str) -> dict[str, Any]:
        recovery = self.storage.get_problem_recovery(problem_id)
        if recovery is None:
            return self._not_found_result("problem_recovery", problem_id)
        return self._operation_result(
            success=True,
            status="ok",
            message=f"Recovery action for problem '{problem_id}' retrieved",
            data=recovery.to_dict(),
            recovery_action=recovery.to_dict(),
        )

    def replay_problem(self, problem_id: str) -> dict[str, Any]:
        record = self.storage.get_problem_record(problem_id)
        if record is None:
            return self._not_found_result("problem", problem_id)
        assets = self.storage.get_problem_assets(problem_id)
        if assets is None:
            return self._not_found_result("problem", problem_id)
        if not self._supports_problem_replay(assets):
            return self._operation_result(
                success=False,
                status="unsupported",
                message=f"Problem '{problem_id}' does not support replay",
                error="problem_replay_unsupported",
                error_code="problem_replay_unsupported",
            )

        replay = (
            assets.recovery.get("replay") if isinstance(assets.recovery, dict) else {}
        )
        if not isinstance(replay, dict) or not replay.get("url"):
            return self._operation_result(
                success=False,
                status="invalid",
                message=f"Problem '{problem_id}' has no replayable request",
                error="problem_replay_missing_request",
                error_code="problem_replay_missing_request",
            )

        try:
            import requests  # type: ignore[import-untyped]
        except ImportError:
            return self._operation_result(
                success=False,
                status="error",
                message="requests module not installed",
                error="requests_not_installed",
                error_code="requests_not_installed",
            )

        method = str(replay.get("method", "GET")).upper()
        url = str(replay["url"])
        headers = replay.get("headers", {})
        params = replay.get("params", {})
        body = replay.get("body", {})
        timeout = replay.get("timeout", 30)

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers if isinstance(headers, dict) else {},
                params=params if isinstance(params, dict) else {},
                json=body if isinstance(body, dict) and body else None,
                timeout=timeout if isinstance(timeout, int | float) else 30,
            )
        except Exception as exc:
            failure_result = self._operation_result(
                success=False,
                status="failed",
                message=f"Replay failed for problem '{problem_id}'",
                error=str(exc),
                error_code="problem_replay_failed",
            )
            recovery_action = self._record_problem_recovery_action(
                record,
                assets,
                action_type="replay",
                success=False,
                status="failed",
                result={
                    "mode": "request_replay",
                    "request": replay,
                    "error": str(exc),
                },
            )
            failure_result["recovery_action"] = recovery_action.to_dict()
            return failure_result

        content_type = response.headers.get("content-type", "")
        response_body: Any
        if content_type.startswith("application/json"):
            try:
                response_body = response.json()
            except ValueError:
                response_body = response.text
        else:
            response_body = response.text

        replay_result = {
            "problem_id": problem_id,
            "request": replay,
            "response": {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": response_body,
            },
        }
        comparison = self._build_api_replay_comparison(assets, replay_result)
        replay_result["comparison"] = comparison
        replay_result["reproduced"] = comparison["expectation"]["reproduced"]
        replay_result["investigation"] = self._build_problem_investigation_summary(
            {
                "problem_id": problem_id,
                "problem_type": assets.problem_type,
                "summary": assets.summary,
                "preservation": assets.details.get("preservation", {})
                if isinstance(assets.details, dict)
                else {},
                "capabilities": assets.metadata.get("capabilities", {})
                if isinstance(assets.metadata, dict)
                else {},
                "latest_action": f"replay:{'completed'}",
            },
            view="replay",
            reproduction_summary=self._build_problem_reproduction_summary(
                self._problem_assets_payload(assets)
            ),
            comparison=comparison,
        )
        recovery_action = self._record_problem_recovery_action(
            record,
            assets,
            action_type="replay",
            success=True,
            status="completed",
            result=replay_result,
        )
        return self._operation_result(
            success=True,
            status="ok",
            message=f"Replay completed for problem '{problem_id}'",
            data=replay_result,
            replay=replay_result,
            recovery_action=recovery_action.to_dict(),
        )

    def recover_problem(self, problem_id: str) -> dict[str, Any]:
        record = self.storage.get_problem_record(problem_id)
        if record is None:
            return self._not_found_result("problem", problem_id)
        assets = self.storage.get_problem_assets(problem_id)
        if assets is None:
            return self._not_found_result("problem_assets", problem_id)
        if not self._supports_problem_recovery(assets):
            return self._operation_result(
                success=False,
                status="unsupported",
                message=f"Problem '{problem_id}' does not support recover",
                error="problem_recover_unsupported",
                error_code="problem_recover_unsupported",
            )

        recovery = self._build_recovery_plan(record, assets)
        recovery_action = self._record_problem_recovery_action(
            record,
            assets,
            action_type="recover",
            success=True,
            status="prepared",
            result=recovery,
        )
        return self._operation_result(
            success=True,
            status="ok",
            message=f"Recovery plan prepared for problem '{problem_id}'",
            data=recovery,
            recovery=recovery,
            recovery_action=recovery_action.to_dict(),
        )

    def destroy_environment(self) -> dict[str, Any]:
        record = self.storage.load_environment()
        if record is None:
            return self._operation_result(
                success=False,
                status="not_initialized",
                message=f"Environment '{self.root_path}' is not initialized",
                error_code="environment_not_initialized",
            )

        cleanup_messages: list[str] = []
        isolation_cleanup = self._cleanup_isolation_environment(record)
        cleanup_messages.extend(isolation_cleanup["messages"])
        objects = self.storage.load_objects()
        for object_name, object_record in objects.items():
            if object_record.status == "running":
                stop_result = self.stop_object(object_name)
                cleanup_messages.append(stop_result["message"])
            uninstall_result = self.uninstall_object(object_name)
            cleanup_messages.append(uninstall_result["message"])

        tools = self.storage.load_tools()
        for tool_name, tool_record in tools.items():
            if tool_record.status == "running":
                stop_result = self.stop_tool(tool_name)
                cleanup_messages.append(stop_result["message"])
            uninstall_result = self.uninstall_tool(tool_name)
            cleanup_messages.append(uninstall_result["message"])

        self._remove_path(self.root_path / "reports")
        self._remove_path(self.root_path / "logs")
        self._remove_path(self.root_path / ".ptest" / "cases.json")
        self._remove_path(self.root_path / ".ptest" / "cases.yaml")
        self.storage.clear_workspace_state()

        destroyed_record = EnvironmentRecord(
            root_path=str(self.root_path),
            status="destroyed",
            isolation_level=record.isolation_level,
            config_file=record.config_file,
            created_at=record.created_at,
            updated_at=datetime.now().isoformat(),
            metadata={
                **record.metadata,
                "destroyed_at": datetime.now().isoformat(),
                "isolation_cleanup": isolation_cleanup,
            },
        )
        self.storage.save_environment(destroyed_record)
        return self._operation_result(
            success=True,
            status="destroyed",
            message=f"Environment '{self.root_path}' destroyed",
            data=destroyed_record.to_dict(),
            cleanup_messages=cleanup_messages,
            isolation_cleanup=isolation_cleanup,
        )

    def get_workspace_status(self) -> dict[str, Any]:
        env_status = self.get_environment_status()
        if not env_status.get("initialized", False):
            return {
                "environment": env_status,
                "objects": self.list_objects(),
                "tools": self.list_tools(),
                "cases": [],
            }
        return {
            "environment": env_status,
            "objects": self.list_objects(),
            "tools": self.list_tools(),
            "cases": self.list_cases(),
            "suites": self.list_suites(),
        }

    def _bootstrap_environment(self) -> EnvironmentManager:
        env_manager = EnvironmentManager()
        env_manager.init_environment(self.root_path)
        self.storage.ensure_layout()
        return env_manager

    def _get_object_manager(self) -> ObjectManager:
        return ObjectManager(self._bootstrap_environment())

    def _get_tool_manager(self) -> ToolManager:
        return ToolManager(self._bootstrap_environment())

    def _get_suite_manager(self) -> SuiteManager:
        return SuiteManager(storage_dir=self.root_path / ".ptest" / "suites")

    def _get_data_template_manager(self) -> DataTemplate:
        return DataTemplate(self.root_path / ".ptest" / "data_templates")

    def _get_contract_manager(self) -> ContractManager:
        return ContractManager(storage_dir=self.root_path / ".ptest" / "contracts")

    def _get_isolation_manager(self) -> IsolationManager:
        if self._isolation_manager is None:
            self._isolation_manager = IsolationManager(self.config)
        return self._isolation_manager

    def _mock_dir(self) -> Path:
        path = self.root_path / ".ptest" / "mocks"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _mock_config_path(self, name: str) -> Path:
        return self._mock_dir() / f"{name}.json"

    def _mock_state_path(self, name: str) -> Path:
        return self._mock_dir() / f"{name}.state.json"

    def _load_mock_state(self, name: str) -> dict[str, Any]:
        state_path = self._mock_state_path(name)
        if not state_path.exists():
            return {}
        return self.storage._read_json(state_path) or {}

    def _save_mock_state(self, name: str, updates: dict[str, Any]) -> dict[str, Any]:
        state = self._load_mock_state(name)
        state.update(updates)
        state["updated_at"] = datetime.now().isoformat()
        self.storage._write_json(self._mock_state_path(name), state)
        return state

    def _mock_status_payload(self, name: str, server: MockServer) -> dict[str, Any]:
        state = self._load_mock_state(name)
        reachable = self._is_mock_server_reachable(
            server.config.host, server.config.port
        )
        runtime_status = (
            "running" if server.is_running() else state.get("status", "stopped")
        )
        if runtime_status == "running" and not server.is_running() and not reachable:
            runtime_status = "stale"
        return {
            **server.config.to_dict(),
            "running": runtime_status == "running",
            "status": runtime_status,
            "reachable": reachable,
            "request_history_count": len(server.get_request_history()),
            "runtime_state": state,
        }

    def _is_mock_server_reachable(self, host: str, port: int) -> bool:
        return self._is_host_port_reachable(host, port)

    def _is_host_port_reachable(self, host: str, port: int) -> bool:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            return False

    def _change_object_state(self, name: str, action: str) -> dict[str, Any]:
        record = self.storage.get_object(name)
        if record is None:
            self._record_environment_dependency_problem(
                problem_type="dependency_object",
                summary=f"Dependency object '{name}' is missing for action '{action}'",
                details={
                    "phase": action,
                    "action": action,
                    "object_name": name,
                    "message": f"Object '{name}' does not exist",
                },
                recovery={
                    "supported": False,
                    "mode": "minimal_environment_recovery",
                    "action": action,
                    "object_name": name,
                    "required_state": "installed",
                },
                object_refs=[name],
            )
            return self._not_found_result("object", name)

        obj = self._materialize_object(record)
        if record.type_name in {"database", "database_server", "database_client"}:
            self._recover_object_runtime(obj, record)

        # ── runtime preflight gate (start / restart only) ───────────────
        if action in {"start", "restart"} and self._supports_runtime_preflight(record):
            preflight = self._build_object_runtime_preflight(record, scope=action)
            metadata_for_preflight = (
                record.metadata if isinstance(record.metadata, dict) else {}
            )
            metadata_for_preflight.setdefault("runtime_preflight", {})
            metadata_for_preflight["runtime_preflight"]["last_check"] = preflight
            record.metadata = metadata_for_preflight
            if preflight["summary"]["required_failed"] > 0:
                failed_checks = [
                    c["code"]
                    for c in preflight["checks"]
                    if c.get("status") == "failed" and c.get("required", False)
                ]
                problem_type = self._classify_preflight_problem_type(
                    preflight["checks"]
                )
                self._record_environment_dependency_problem(
                    problem_type=problem_type,
                    summary=f"Object '{name}' failed runtime preflight for '{action}'",
                    details={
                        "phase": "preflight",
                        "action": action,
                        "object": record.to_dict(),
                        "runtime_preflight": preflight,
                        "message": f"Object '{name}' failed runtime preflight",
                    },
                    recovery={
                        "supported": False,
                        "mode": "minimal_environment_recovery",
                        "action": "fix_runtime_preflight",
                        "object_name": name,
                        "required_state": "ready_to_start",
                        "failed_checks": failed_checks,
                    },
                    object_refs=[name],
                )
                record.updated_at = datetime.now().isoformat()
                self.storage.upsert_object(record)
                return self._operation_result(
                    success=False,
                    status="error",
                    message=f"Object '{name}' failed runtime preflight for '{action}'",
                    data=record.to_dict(),
                    object=record.to_dict(),
                    checks=preflight,
                    runtime_preflight=preflight,
                    error_code=f"object_{action}_preflight_failed",
                )

        operation = getattr(obj, action)
        result = operation()
        success = result.startswith("✓")
        if success:
            status_map = {
                "start": OBJECT_STATUS_RUNNING,
                "stop": OBJECT_STATUS_STOPPED,
                "restart": OBJECT_STATUS_RUNNING,
            }
            record.status = status_map[action]
            record.installed = True
        else:
            record.status = self._resolve_object_action_failure_status(
                record,
                obj,
                action,
                result,
            )
        metadata = record.metadata.copy()
        metadata.update(self._collect_object_metadata(obj))
        existing_runtime_backend = metadata.get("runtime_backend")
        last_preflight = (
            self._build_runtime_backend_preflight_summary(
                success=success,
                message=result,
            )
            if action in {"start", "restart"}
            else None
        )
        runtime_backend_summary = self._build_object_runtime_backend_summary(
            record,
            last_preflight=last_preflight,
        )
        if (
            action not in {"start", "restart"}
            and isinstance(existing_runtime_backend, dict)
            and "last_preflight" not in runtime_backend_summary
        ):
            existing_last_preflight = existing_runtime_backend.get("last_preflight")
            if existing_last_preflight is not None:
                runtime_backend_summary["last_preflight"] = existing_last_preflight
        metadata["runtime_backend"] = runtime_backend_summary
        metadata["crash_capture"] = self._merge_object_crash_capture_capability(
            record,
            metadata.get("crash_capture"),
        )
        if action in {"start", "restart"}:
            metadata["crash_capture"] = self._attempt_object_crash_capture_enable(
                metadata["crash_capture"]
            )
        if not success and is_failure_preserved_object_status(record.status):
            metadata["failure_state"] = self._build_failure_state_metadata(
                phase=action,
                message=result,
            )
        if success and action == "stop":
            metadata.setdefault("boundary_checks", {})
            metadata["boundary_checks"]["stop"] = self._collect_mysql_boundary_checks(
                record,
                action="stop",
                object_removed=False,
            )
        record.metadata = metadata
        record.updated_at = datetime.now().isoformat()
        if success and action == "start":
            connectivity_issue = self._detect_object_connectivity_issue(record)
            if connectivity_issue is not None:
                record.status = self._resolve_start_failure_status(
                    record,
                    obj,
                    result,
                    connectivity_issue=connectivity_issue,
                )
                record.metadata["connectivity_check"] = connectivity_issue
                validation_message = (
                    f"✗ Object '{name}' started but is unreachable at "
                    f"{connectivity_issue['target']}: {connectivity_issue['message']}"
                )
                if is_failure_preserved_object_status(record.status):
                    record.metadata["failure_state"] = (
                        self._build_failure_state_metadata(
                            phase="start",
                            message=validation_message,
                        )
                    )
                self.storage.upsert_object(record)
                self._record_environment_dependency_problem(
                    problem_type="dependency_object",
                    summary=f"Dependency object '{name}' failed pre-run validation",
                    details={
                        "phase": "pre-run validation",
                        "action": action,
                        "object": record.to_dict(),
                        "message": validation_message,
                        "validation": connectivity_issue,
                    },
                    recovery={
                        "supported": False,
                        "mode": "minimal_environment_recovery",
                        "action": "validate_object_connectivity",
                        "object_name": name,
                        "required_state": "reachable",
                        "target": connectivity_issue["target"],
                    },
                    object_refs=[name],
                )
                return self._operation_result(
                    success=False,
                    status="error",
                    message=validation_message,
                    data=record.to_dict(),
                    object=record.to_dict(),
                    error_code="object_start_validation_failed",
                )
        self.storage.upsert_object(record)
        if not success:
            problem_type = self._classify_object_state_problem(record, action, result)
            config = record.config if isinstance(record.config, dict) else {}
            missing_libraries = self._extract_missing_shared_libraries(result)
            dependency_requirements = config.get("dependency_requirements", {})
            self._record_environment_dependency_problem(
                problem_type=problem_type,
                summary=f"Dependency object '{name}' failed during '{action}'",
                details={
                    "phase": action,
                    "action": action,
                    "object": record.to_dict(),
                    "message": result,
                    "missing_libraries": missing_libraries,
                    "dependency_requirements": dependency_requirements
                    if isinstance(dependency_requirements, dict)
                    else {},
                },
                recovery={
                    "supported": False,
                    "mode": "minimal_environment_recovery",
                    "action": (
                        "install_dependencies"
                        if problem_type == "dependency_configuration"
                        and missing_libraries
                        else action
                    ),
                    "object_name": name,
                    "required_state": "running" if action == "start" else "installed",
                    "missing_libraries": missing_libraries,
                    "dependency_requirements": dependency_requirements
                    if isinstance(dependency_requirements, dict)
                    else {},
                },
                object_refs=[name],
            )
        return self._operation_result(
            success=success,
            status=record.status if success else "error",
            message=result,
            data=record.to_dict(),
            object=record.to_dict(),
            checks=record.metadata.get("boundary_checks", {}).get(action)
            if success and action == "stop"
            else None,
            error_code=f"object_{action}_failed" if not success else None,
        )

    def _detect_object_connectivity_issue(
        self, record: ManagedObjectRecord
    ) -> dict[str, Any] | None:
        if record.type_name not in {"service", "web"}:
            return None
        config = record.config if isinstance(record.config, dict) else {}
        host = config.get("host")
        port = config.get("port")
        if not isinstance(host, str) or not host:
            return None
        if not isinstance(port, int) or port <= 0:
            return None
        if self._is_host_port_reachable(host, port):
            return None
        return {
            "host": host,
            "port": port,
            "target": f"{host}:{port}",
            "reachable": False,
            "message": "target endpoint is not reachable",
        }

    def _collect_mysql_boundary_checks(
        self,
        record: ManagedObjectRecord,
        *,
        action: str,
        object_removed: bool,
    ) -> dict[str, Any] | None:
        config = record.config if isinstance(record.config, dict) else {}
        if str(config.get("db_type", "")).lower() != "mysql":
            return None

        scenario = config.get("scenario", {})
        if not isinstance(scenario, dict):
            scenario = {}
        boundary_config = scenario.get("boundary_checks", {})
        if not isinstance(boundary_config, dict):
            boundary_config = {}

        managed_instance = config.get("managed_instance", {})
        if not isinstance(managed_instance, dict):
            managed_instance = {}

        workspace_path = (
            Path(str(config.get("workspace_path", self.root_path)))
            .expanduser()
            .resolve()
        )
        relevant_paths = {
            **{key: str(value) for key, value in managed_instance.items()},
            "config_file": str(config.get("config_file", "")),
            "log_file": str(config.get("log_file", "")),
            "pid_file": str(config.get("pid_file", "")),
            "staged_package_path": str(config.get("staged_package_path", "")),
        }
        workspace_violations = [
            path
            for path in relevant_paths.values()
            if path and not self._path_within_workspace(workspace_path, Path(path))
        ]

        pid_file = Path(str(config.get("pid_file", ""))).expanduser().resolve()
        pid = self._read_pid_file(pid_file)
        process_running = pid is not None and self._is_pid_running(pid)
        host = str(config.get("server_host", "127.0.0.1"))
        port = self._coerce_mysql_port(config.get("server_port", config.get("port")))
        port_released = not self._is_host_port_reachable(host, port)

        instance_root_value = str(managed_instance.get("instance_root", ""))
        instance_root = (
            Path(instance_root_value).expanduser().resolve()
            if instance_root_value
            else None
        )
        managed_paths_removed = bool(
            instance_root is not None and not instance_root.exists()
        )

        checks: dict[str, Any] = {
            "action": action,
            "workspace_boundary": {
                "enabled": bool(boundary_config.get("check_workspace_boundary", True)),
                "ok": not workspace_violations,
                "violations": workspace_violations,
                "workspace_path": str(workspace_path),
            },
            "process_cleanup": {
                "enabled": bool(boundary_config.get("check_process_cleanup", True)),
                "ok": not process_running and not pid_file.exists(),
                "pid": pid,
                "pid_file": str(pid_file),
                "pid_file_exists": pid_file.exists(),
                "process_running": process_running,
            },
            "port_release": {
                "enabled": bool(boundary_config.get("check_port_release", True)),
                "ok": port_released,
                "host": host,
                "port": port,
                "released": port_released,
            },
            "object_cleanup": {
                "enabled": bool(boundary_config.get("check_object_cleanup", True)),
                "ok": (
                    managed_paths_removed
                    if action == "uninstall"
                    else record.status == "stopped"
                ),
                "object_removed": object_removed,
                "managed_paths_removed": (
                    managed_paths_removed if action == "uninstall" else None
                ),
                "instance_root": str(instance_root)
                if instance_root is not None
                else "",
            },
        }
        checks["all_passed"] = all(
            entry["ok"]
            for entry in checks.values()
            if isinstance(entry, dict) and entry.get("enabled", True)
        )
        return checks

    def _path_within_workspace(self, workspace_path: Path, path: Path) -> bool:
        try:
            path.resolve().relative_to(workspace_path.resolve())
            return True
        except ValueError:
            return False

    def _read_pid_file(self, path: Path) -> int | None:
        try:
            return int(path.read_text(encoding="utf-8").strip())
        except (FileNotFoundError, ValueError):
            return None

    def _is_pid_running(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def _change_tool_state(self, name: str, action: str) -> dict[str, Any]:
        record = self.storage.get_tool(name)
        if record is None:
            return self._not_found_result("tool", name)

        tool = self._materialize_tool(record)
        operation = getattr(tool, action)
        result = operation()
        success = result.startswith("✓")
        if success:
            status_map = {
                "start": "running",
                "stop": "stopped",
                "restart": "running",
            }
            record.status = status_map[action]
            record.installed = True
        else:
            record.status = "error"
        record.updated_at = datetime.now().isoformat()
        self.storage.upsert_tool(record)
        return self._operation_result(
            success=success,
            status=record.status,
            message=result,
            data=record.to_dict(),
            tool=record.to_dict(),
            error_code=f"tool_{action}_failed" if not success else None,
        )

    def _resolve_install_failure_status(
        self,
        normalized_type: str,
        install_params: dict[str, Any],
        result: str,
        materialized: Any | None,
    ) -> str:
        if normalized_type != "database_server":
            return OBJECT_STATUS_ERROR

        if not self._install_failure_has_preservable_artifacts(
            install_params,
            materialized,
        ):
            return OBJECT_STATUS_ERROR
        return OBJECT_STATUS_INSTALL_FAILED_PRESERVED

    def _resolve_object_action_failure_status(
        self,
        record: ManagedObjectRecord,
        obj: Any,
        action: str,
        result: str,
    ) -> str:
        if action == "start":
            return self._resolve_start_failure_status(record, obj, result)
        return OBJECT_STATUS_ERROR

    def _resolve_start_failure_status(
        self,
        record: ManagedObjectRecord,
        obj: Any,
        result: str,
        *,
        connectivity_issue: dict[str, Any] | None = None,
    ) -> str:
        if record.status not in {
            OBJECT_STATUS_INSTALLED,
            OBJECT_STATUS_STOPPED,
        }:
            return OBJECT_STATUS_ERROR

        if not self._start_failure_has_preservable_artifacts(
            record,
            obj,
            connectivity_issue=connectivity_issue,
        ):
            return OBJECT_STATUS_ERROR
        return OBJECT_STATUS_START_FAILED_PRESERVED

    def _install_failure_has_preservable_artifacts(
        self,
        install_params: dict[str, Any],
        materialized: Any | None,
    ) -> bool:
        path_candidates: list[str] = []

        managed_instance = install_params.get("managed_instance")
        if isinstance(managed_instance, dict):
            instance_root = managed_instance.get("instance_root")
            if isinstance(instance_root, str) and instance_root:
                path_candidates.append(instance_root)

        for key in ("staged_package_path", "install_root", "config_file"):
            value = install_params.get(key)
            if isinstance(value, str) and value:
                path_candidates.append(value)

        runtime_snapshot = (
            self._collect_object_metadata(materialized) if materialized else {}
        )
        runtime_details = runtime_snapshot.get("runtime", {}).get("details", {})
        if isinstance(runtime_details, dict):
            for key in ("staged_package_path", "install_root", "config_file"):
                value = runtime_details.get(key)
                if isinstance(value, str) and value:
                    path_candidates.append(value)

        return self._any_path_exists(path_candidates)

    def _start_failure_has_preservable_artifacts(
        self,
        record: ManagedObjectRecord,
        obj: Any,
        *,
        connectivity_issue: dict[str, Any] | None = None,
    ) -> bool:
        if connectivity_issue is not None:
            return True

        path_candidates: list[str] = []
        config = record.config if isinstance(record.config, dict) else {}
        for key in ("config_file", "install_root", "log_file", "mysql_binary"):
            value = config.get(key)
            if isinstance(value, str) and value:
                path_candidates.append(value)

        runtime_snapshot = self._collect_object_metadata(obj)
        runtime_details = runtime_snapshot.get("runtime", {}).get("details", {})
        if isinstance(runtime_details, dict):
            for key in ("config_file", "install_root", "log_file", "mysql_binary"):
                value = runtime_details.get(key)
                if isinstance(value, str) and value:
                    path_candidates.append(value)

        if config.get("runtime_library_paths") or config.get("dependency_requirements"):
            return True

        return self._any_path_exists(path_candidates)

    def _any_path_exists(self, values: list[str]) -> bool:
        for value in values:
            try:
                if Path(value).expanduser().exists():
                    return True
            except OSError:
                continue
        return False

    def _build_object_status_payload(
        self,
        record: ManagedObjectRecord,
    ) -> dict[str, Any]:
        payload = record.to_dict()
        linked_problems = self._list_recent_problem_summaries_for_object(record.name)
        payload["available_actions"] = {
            "clear": is_clearable_object_status(record.status),
            "reset": is_resettable_object_status(record.status),
        }
        metadata = payload.get("metadata", {})
        if isinstance(metadata, dict):
            failure_state = metadata.get("failure_state")
            if isinstance(failure_state, dict):
                payload["failure_state"] = failure_state
        payload["suggested_actions"] = self._build_object_suggested_actions(
            record.status,
            linked_problems,
        )
        if linked_problems:
            payload["linked_problems"] = linked_problems
        payload["diagnostics"] = self._build_object_status_diagnostics(
            record,
            linked_problems=linked_problems,
        )
        return payload

    def _build_object_suggested_actions(
        self,
        status: str,
        linked_problems: list[dict[str, Any]],
    ) -> list[str]:
        actions: list[str] = []
        if is_clearable_object_status(status):
            actions.append("clear")
        if is_resettable_object_status(status):
            actions.append("reset")
        if is_failure_preserved_object_status(status):
            actions.append("inspect_preserved_artifacts")
        if linked_problems:
            actions.append(f"review_problem:{linked_problems[0]['problem_id']}")
        return actions

    def _list_recent_problem_summaries_for_object(
        self,
        object_name: str,
        *,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        matches: list[dict[str, Any]] = []
        for record in self.storage.load_problem_records().values():
            if object_name not in record.object_refs:
                continue
            matches.append(
                {
                    "problem_id": record.problem_id,
                    "problem_type": record.problem_type,
                    "summary": record.summary,
                    "latest_action": record.latest_action,
                    "created_at": record.created_at,
                }
            )
        matches.sort(key=lambda item: item["created_at"], reverse=True)
        return matches[:limit]

    def _build_failure_state_metadata(
        self,
        *,
        phase: str,
        message: str,
    ) -> dict[str, Any]:
        return {
            "phase": phase,
            "message": message,
            "preserved_at": datetime.now().isoformat(),
        }

    def _cleanup_preserved_object_state(
        self,
        record: ManagedObjectRecord,
        *,
        remove_installation: bool,
    ) -> dict[str, Any]:
        config = record.config if isinstance(record.config, dict) else {}
        details: dict[str, Any] = {
            "remove_installation": remove_installation,
            "runtime_cleanup": {},
            "managed_paths_removed": False,
        }
        runtime_cleanup = self._cleanup_object_runtime_artifacts(config)
        details["runtime_cleanup"] = runtime_cleanup
        if not runtime_cleanup["success"]:
            return {
                "success": False,
                "message": runtime_cleanup["message"],
                "details": details,
            }

        if remove_installation:
            removal = self._remove_managed_object_paths(config)
            details["managed_paths_removed"] = removal["removed"]
            if not removal["success"]:
                return {
                    "success": False,
                    "message": removal["message"],
                    "details": details,
                }

        return {
            "success": True,
            "message": "Preserved object state cleared",
            "details": details,
        }

    def _cleanup_object_runtime_artifacts(
        self,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        pid_file = self._optional_path_from_config(config.get("pid_file"))
        socket_file = self._optional_path_from_config(config.get("socket_file"))
        pid = self._read_pid_file(pid_file) if pid_file is not None else None
        process_stopped = True
        if pid is not None and self._is_pid_running(pid):
            try:
                os.kill(pid, 15)
            except OSError as exc:
                return {
                    "success": False,
                    "message": f"Failed to stop preserved process {pid}: {exc}",
                    "pid": pid,
                }
            for _ in range(20):
                if not self._is_pid_running(pid):
                    break
                time.sleep(0.1)
            process_stopped = not self._is_pid_running(pid)
            if not process_stopped:
                return {
                    "success": False,
                    "message": f"Preserved process {pid} did not exit in time",
                    "pid": pid,
                }

        removed_files: list[str] = []
        for path in (pid_file, socket_file):
            if path is None or not path.exists():
                continue
            try:
                path.unlink()
                removed_files.append(str(path))
            except OSError as exc:
                return {
                    "success": False,
                    "message": f"Failed to remove preserved runtime file {path}: {exc}",
                    "pid": pid,
                }
        return {
            "success": True,
            "message": "Preserved runtime artifacts cleaned",
            "pid": pid,
            "process_stopped": process_stopped,
            "removed_files": removed_files,
        }

    def _remove_managed_object_paths(self, config: dict[str, Any]) -> dict[str, Any]:
        managed_instance = config.get("managed_instance", {})
        if isinstance(managed_instance, dict):
            instance_root = self._optional_path_from_config(
                managed_instance.get("instance_root")
            )
            if instance_root is not None and instance_root.exists():
                try:
                    shutil.rmtree(instance_root)
                    return {
                        "success": True,
                        "message": "Managed instance root removed",
                        "removed": True,
                        "path": str(instance_root),
                    }
                except OSError as exc:
                    return {
                        "success": False,
                        "message": f"Failed to remove managed instance root: {exc}",
                        "removed": False,
                    }

        removed_any = False
        for key in ("staged_package_path", "config_file", "install_root"):
            path = self._optional_path_from_config(config.get(key))
            if path is None or not path.exists():
                continue
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
                removed_any = True
            except OSError as exc:
                return {
                    "success": False,
                    "message": f"Failed to remove preserved install artifact {path}: {exc}",
                    "removed": removed_any,
                }
        return {
            "success": True,
            "message": "Managed object artifacts removed",
            "removed": removed_any,
        }

    def _optional_path_from_config(self, value: Any) -> Path | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            return Path(value).expanduser().resolve()
        except OSError:
            return None

    def _materialize_object(self, record: ManagedObjectRecord) -> Any:
        manager = self._get_object_manager()
        obj = manager.create_object(record.type_name, record.name, record.config)
        self._apply_object_record(obj, record)
        return obj

    def _refresh_object_record(
        self, record: ManagedObjectRecord
    ) -> ManagedObjectRecord:
        obj = self._materialize_object(record)
        self._recover_object_runtime(obj, record)
        metadata = record.metadata.copy()
        metadata.update(self._collect_object_metadata(obj))
        record.metadata = metadata
        record.updated_at = datetime.now().isoformat()
        self.storage.upsert_object(record)
        return record

    def _apply_object_record(self, obj: Any, record: ManagedObjectRecord) -> None:
        if hasattr(obj, "installed"):
            obj.installed = record.installed
        if hasattr(obj, "status"):
            obj.status = record.status
        if hasattr(obj, "db_config") and record.config:
            obj.db_config = record.config.copy()

    def _recover_object_runtime(self, obj: Any, record: ManagedObjectRecord) -> None:
        warnings: list[str] = []
        recovery: dict[str, Any] = {
            "mode": "metadata_only",
            "recovered": True,
            "warnings": warnings,
        }
        runtime = record.metadata.get("runtime", {})
        effective_status = record.status

        if record.type_name == "database" and record.installed and record.config:
            install_result = obj.install(record.config)
            if isinstance(install_result, str) and install_result.startswith("✓"):
                recovery["mode"] = "rebuild_connector"
                if record.status == OBJECT_STATUS_RUNNING:
                    start_result = obj.start()
                    if not (
                        isinstance(start_result, str) and start_result.startswith("✓")
                    ):
                        effective_status = OBJECT_STATUS_INSTALLED
                        recovery["recovered"] = False
                        warnings.append(
                            "Database runtime could not be resumed; downgraded to installed"
                        )
            else:
                effective_status = OBJECT_STATUS_ERROR
                recovery["recovered"] = False
                warnings.append(str(install_result))
        elif (
            record.type_name == "database_server" and record.installed and record.config
        ):
            install_result = obj.install(record.config)
            if isinstance(install_result, str) and install_result.startswith("✓"):
                recovery["mode"] = "rebuild_server_component"
                component = getattr(obj, "server_component", None)
                if record.status == OBJECT_STATUS_RUNNING and component is not None:
                    component.status = OBJECT_STATUS_RUNNING
                    success, message = component.health_check()
                    if success:
                        obj.status = OBJECT_STATUS_RUNNING
                    else:
                        obj.status = OBJECT_STATUS_INSTALLED
                        effective_status = OBJECT_STATUS_INSTALLED
                        recovery["recovered"] = False
                        warnings.append(message)
            else:
                effective_status = OBJECT_STATUS_ERROR
                recovery["recovered"] = False
                warnings.append(str(install_result))
        elif (
            record.type_name == "database_client" and record.installed and record.config
        ):
            install_result = obj.install(record.config)
            if isinstance(install_result, str) and install_result.startswith("✓"):
                recovery["mode"] = "rebuild_client_connection"
                if record.status == OBJECT_STATUS_RUNNING:
                    start_result = obj.start()
                    if not (
                        isinstance(start_result, str) and start_result.startswith("✓")
                    ):
                        effective_status = OBJECT_STATUS_INSTALLED
                        recovery["recovered"] = False
                        warnings.append(
                            "Database client connection could not be resumed"
                        )
            else:
                effective_status = OBJECT_STATUS_ERROR
                recovery["recovered"] = False
                warnings.append(str(install_result))
        elif record.status == OBJECT_STATUS_RUNNING:
            effective_status = (
                OBJECT_STATUS_INSTALLED if record.installed else OBJECT_STATUS_STOPPED
            )
            recovery["mode"] = "downgraded_nonrecoverable_runtime"
            recovery["recovered"] = False
            warnings.append(
                f"Object type '{record.type_name}' does not support runtime resume; downgraded status"
            )

        record.status = effective_status
        record.installed = bool(getattr(obj, "installed", record.installed))
        if hasattr(obj, "status"):
            obj.status = effective_status
        record.metadata["recovery"] = recovery
        record.metadata["runtime"] = self._collect_object_runtime_snapshot(obj, runtime)

    def _collect_object_metadata(self, obj: Any | None) -> dict[str, Any]:
        if obj is None:
            return {}
        return {
            "runtime": self._collect_object_runtime_snapshot(obj),
        }

    def _capture_object_artifacts_before(
        self,
        case_definition: dict[str, Any] | None,
    ) -> dict[str, Any]:
        selection = self._build_object_artifact_selection(case_definition)
        return {
            "selection": selection,
            "before": self._capture_object_artifact_snapshot(
                selection.get("object_refs", [])
            ),
        }

    def _build_object_artifacts_record(
        self,
        *,
        execution_id: str,
        case_definition: dict[str, Any] | None,
        before_capture: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if isinstance(before_capture, dict):
            selection = before_capture.get("selection", {})
            before = before_capture.get("before", {})
        else:
            selection = self._build_object_artifact_selection(case_definition)
            before = self._capture_object_artifact_snapshot(
                selection.get("object_refs", [])
            )
        if not isinstance(selection, dict):
            selection = self._build_object_artifact_selection(case_definition)
        if not isinstance(before, dict):
            before = self._capture_object_artifact_snapshot(
                selection.get("object_refs", [])
            )
        after = self._capture_object_artifact_snapshot(selection.get("object_refs", []))
        return {
            "execution_id": execution_id,
            "selection": selection,
            "before": before,
            "after": after,
            "changes": self._build_object_artifact_changes(before, after),
        }

    def _capture_data_state_snapshot(
        self,
        case_definition: dict[str, Any] | None,
        *,
        phase: str,
    ) -> dict[str, Any] | None:
        if not isinstance(case_definition, dict):
            return None
        case_payload = self._unwrap_case_definition(case_definition)
        if case_payload.get("type") != "database":
            return None
        db_type = str(case_payload.get("db_type", "")).lower()
        database_path = case_payload.get("database", "")
        if db_type == "sqlite":
            if not database_path:
                return {
                    "phase": phase,
                    "capture_status": "unavailable",
                    "reason": "database path not specified",
                }
            try:
                return self._capture_sqlite_state_snapshot(database_path, phase=phase)
            except Exception as exc:
                return {
                    "phase": phase,
                    "capture_status": "unavailable",
                    "reason": f"snapshot capture failed: {exc}",
                }
        if db_type == "mysql":
            return {
                "phase": phase,
                "capture_status": "unsupported",
                "reason": "mysql snapshot not yet supported",
            }
        return {
            "phase": phase,
            "capture_status": "unsupported",
            "reason": f"unsupported db_type: {db_type}",
        }

    _SQLITE_SNAPSHOT_MAX_TABLES = 20
    _SQLITE_SNAPSHOT_MAX_COLUMNS = 30

    def _capture_sqlite_state_snapshot(
        self,
        database_path: str,
        *,
        phase: str,
    ) -> dict[str, Any]:
        from datetime import datetime as _dt

        now = _dt.now().isoformat()
        db_file = Path(database_path)
        if not db_file.exists():
            return {
                "phase": phase,
                "capture_status": "unavailable",
                "captured_at": now,
                "reason": "database file does not exist",
            }
        try:
            file_stat = db_file.stat()
            file_info = {
                "exists": True,
                "size": file_stat.st_size,
                "mtime": _dt.fromtimestamp(file_stat.st_mtime).isoformat(),
            }
        except OSError as e:
            return {
                "phase": phase,
                "capture_status": "unavailable",
                "captured_at": now,
                "reason": f"failed to stat database file: {e}",
            }
        max_tables = self._SQLITE_SNAPSHOT_MAX_TABLES
        max_columns = self._SQLITE_SNAPSHOT_MAX_COLUMNS
        try:
            conn = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT name, type FROM sqlite_master "
                    "WHERE type IN ('table', 'view') ORDER BY type, name"
                )
                raw_objects = cursor.fetchall()
                tables: list[dict[str, Any]] = []
                table_count = 0
                view_count = 0
                for obj_name, obj_type in raw_objects:
                    if obj_type == "table":
                        table_count += 1
                    else:
                        view_count += 1
                    if len(tables) >= max_tables:
                        continue
                    # safe quoting: table names from sqlite_master, not user input
                    safe_name = obj_name.replace('"', '""')
                    try:
                        cursor.execute('PRAGMA table_info("' + safe_name + '")')
                        raw_columns = cursor.fetchall()
                        columns = [
                            {"name": col[1], "type": col[2]}
                            for col in raw_columns[:max_columns]
                        ]
                    except sqlite3.Error:
                        columns = []
                    row_count = 0
                    if obj_type == "table":
                        try:
                            cursor.execute('SELECT COUNT(*) FROM "' + safe_name + '"')
                            row_count = cursor.fetchone()[0]
                        except sqlite3.Error:
                            row_count = -1
                    tables.append(
                        {
                            "name": obj_name,
                            "type": obj_type,
                            "columns": columns,
                            "row_count": row_count,
                        }
                    )
                schema = {
                    "table_count": table_count,
                    "view_count": view_count,
                    "tables": tables,
                }
            finally:
                conn.close()
        except sqlite3.Error as e:
            return {
                "phase": phase,
                "capture_status": "unavailable",
                "captured_at": now,
                "data_source": {"db_type": "sqlite", "database": database_path},
                "file": file_info,
                "reason": f"sqlite query failed: {e}",
            }
        return {
            "phase": phase,
            "capture_status": "available",
            "captured_at": now,
            "data_source": {"db_type": "sqlite", "database": database_path},
            "file": file_info,
            "schema": schema,
            "limits": {
                "max_tables": max_tables,
                "max_columns_per_table": max_columns,
                "row_values_captured": False,
            },
        }

    def _build_data_state_artifacts_record(
        self,
        *,
        execution_id: str,
        case_definition: dict[str, Any] | None,
        before_capture: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not isinstance(case_definition, dict):
            return None
        case_payload = self._unwrap_case_definition(case_definition)
        if case_payload.get("type") != "database":
            return None
        after = self._capture_data_state_snapshot(case_definition, phase="after")
        diff = self._diff_data_state_snapshots(before_capture, after)
        db_type = str(case_payload.get("db_type", "")).lower()
        database_path = case_payload.get("database", "")
        capture_status = "unavailable"
        if after and isinstance(after, dict):
            capture_status = after.get("capture_status", "unavailable")
        return {
            "execution_id": execution_id,
            "capture_status": capture_status,
            "data_source": {
                "db_type": db_type,
                "database": database_path,
                "object_name": case_payload.get("object_name"),
            },
            "before": before_capture,
            "after": after,
            "diff": diff,
            "limits": {
                "max_tables": self._SQLITE_SNAPSHOT_MAX_TABLES,
                "max_columns_per_table": self._SQLITE_SNAPSHOT_MAX_COLUMNS,
                "row_values_captured": False,
            },
        }

    def _diff_data_state_snapshots(
        self,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not isinstance(before, dict) or not isinstance(after, dict):
            missing = []
            if not isinstance(before, dict):
                missing.append("before")
            if not isinstance(after, dict):
                missing.append("after")
            return {
                "capture_complete": False,
                "reason": f"snapshot not available: {', '.join(missing)}",
                "file_changed": False,
                "schema_changed": False,
                "added_tables": [],
                "removed_tables": [],
                "row_count_changes": [],
            }
        before_status = before.get("capture_status")
        after_status = after.get("capture_status")
        if before_status != "available" or after_status != "available":
            return {
                "capture_complete": False,
                "reason": "snapshot capture not available",
                "file_changed": False,
                "schema_changed": False,
                "added_tables": [],
                "removed_tables": [],
                "row_count_changes": [],
            }
        before_file = before.get("file", {})
        after_file = after.get("file", {})
        file_changed = before_file.get("size") != after_file.get(
            "size"
        ) or before_file.get("mtime") != after_file.get("mtime")
        before_schema = before.get("schema", {})
        after_schema = after.get("schema", {})
        before_tables = {
            t["name"]: t
            for t in before_schema.get("tables", [])
            if isinstance(t, dict) and "name" in t
        }
        after_tables = {
            t["name"]: t
            for t in after_schema.get("tables", [])
            if isinstance(t, dict) and "name" in t
        }
        before_names = set(before_tables.keys())
        after_names = set(after_tables.keys())
        added_tables = sorted(after_names - before_names)
        removed_tables = sorted(before_names - after_names)
        schema_changed = bool(added_tables or removed_tables)
        row_count_changes = []
        for table_name in sorted(before_names & after_names):
            before_count = before_tables[table_name].get("row_count", 0)
            after_count = after_tables[table_name].get("row_count", 0)
            if before_count != after_count:
                row_count_changes.append(
                    {
                        "table": table_name,
                        "before": before_count,
                        "after": after_count,
                        "delta": after_count - before_count,
                    }
                )
        return {
            "capture_complete": True,
            "file_changed": file_changed,
            "schema_changed": schema_changed,
            "added_tables": added_tables,
            "removed_tables": removed_tables,
            "row_count_changes": row_count_changes,
        }

    def _summarize_data_state_artifacts(
        self,
        data_state_artifacts: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not isinstance(data_state_artifacts, dict):
            return {"available": False, "capture_status": "unavailable"}
        capture_status = data_state_artifacts.get("capture_status", "unavailable")
        diff = data_state_artifacts.get("diff", {})
        if not isinstance(diff, dict):
            diff = {}
        reason = data_state_artifacts.get("reason")
        if not reason:
            reason = diff.get("reason")
        if not reason:
            for phase_key in ("before", "after"):
                phase = data_state_artifacts.get(phase_key)
                if isinstance(phase, dict) and phase.get("reason"):
                    reason = phase["reason"]
                    break
        return {
            "available": capture_status == "available",
            "capture_status": capture_status,
            "schema_changed": diff.get("schema_changed", False),
            "row_count_changes": diff.get("row_count_changes", []),
            "reason": reason,
        }

    def _build_object_artifact_selection(
        self,
        case_definition: dict[str, Any] | None,
    ) -> dict[str, Any]:
        case_payload = (
            self._unwrap_case_definition(case_definition)
            if isinstance(case_definition, dict)
            else {}
        )
        object_refs: list[str] = []
        for value in (
            case_payload.get("object_name"),
            case_payload.get("service_name"),
        ):
            if isinstance(value, str) and value and value not in object_refs:
                object_refs.append(value)
        bound_object = case_payload.get("bound_object")
        if isinstance(bound_object, dict):
            bound_name = bound_object.get("name")
            if (
                isinstance(bound_name, str)
                and bound_name
                and bound_name not in object_refs
            ):
                object_refs.append(bound_name)
        if object_refs:
            return {
                "mode": "explicit_refs",
                "selection_reason": "case_object_refs",
                "object_refs": object_refs,
            }
        fallback_refs = sorted(self.storage.load_objects().keys())
        return {
            "mode": "all_objects_fallback",
            "selection_reason": "all_objects_fallback",
            "object_refs": fallback_refs,
        }

    def _capture_object_artifact_snapshot(
        self,
        object_refs: Any,
    ) -> dict[str, Any]:
        refs = object_refs if isinstance(object_refs, list) else []
        objects = [
            self._build_object_artifact_summary(str(name))
            for name in refs
            if isinstance(name, str) and name
        ]
        return {
            "captured_at": datetime.now().isoformat(),
            "objects": objects,
        }

    def _build_object_artifact_summary(self, object_name: str) -> dict[str, Any]:
        record = self.storage.get_object(object_name)
        if record is None:
            return {
                "object_name": object_name,
                "object_found": False,
            }
        metadata = record.metadata if isinstance(record.metadata, dict) else {}
        summary = {
            "object_name": record.name,
            "object_found": True,
            "type_name": record.type_name,
            "status": record.status,
            "installed": record.installed,
            "runtime_backend": metadata.get("runtime_backend", {}),
            "runtime": metadata.get("runtime", {}),
            "crash_capture": metadata.get("crash_capture", {}),
            "artifact_sources": self._build_object_artifact_sources(record),
        }
        return summary

    def _build_object_artifact_sources(
        self,
        record: ManagedObjectRecord,
    ) -> dict[str, Any]:
        config = record.config if isinstance(record.config, dict) else {}
        sources: dict[str, Any] = {}
        managed_instance = config.get("managed_instance", {})
        if isinstance(managed_instance, dict):
            for key, value in sorted(managed_instance.items()):
                if not isinstance(value, str) or not value:
                    continue
                if key.endswith("_dir") or key in {
                    "config_file",
                    "data_dir",
                    "dump_dir",
                    "files_dir",
                    "install_dir",
                    "lib_dir",
                }:
                    sources[key] = self._summarize_artifact_path(value)
        crash_capture = (
            record.metadata.get("crash_capture", {})
            if isinstance(record.metadata, dict)
            else {}
        )
        if isinstance(crash_capture, dict):
            dump_dir = crash_capture.get("dump_dir")
            if isinstance(dump_dir, str) and dump_dir and "dump_dir" not in sources:
                sources["dump_dir"] = self._summarize_artifact_path(dump_dir)
        return sources

    def _summarize_artifact_path(self, raw_path: str) -> dict[str, Any]:
        path = Path(raw_path).expanduser()
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        summary: dict[str, Any] = {
            "path": self._workspace_display_path(resolved),
            "exists": resolved.exists(),
        }
        try:
            if not resolved.exists():
                summary.update(
                    {
                        "kind": "missing",
                        "file_count": 0,
                        "total_size": 0,
                        "latest_files": [],
                    }
                )
                return summary
            if resolved.is_file():
                stat = resolved.stat()
                summary.update(
                    {
                        "kind": "file",
                        "file_count": 1,
                        "total_size": stat.st_size,
                        "latest_files": [
                            self._artifact_file_summary(resolved, stat=stat)
                        ],
                    }
                )
                return summary
            if not resolved.is_dir():
                summary.update(
                    {
                        "kind": "other",
                        "file_count": 0,
                        "total_size": 0,
                        "latest_files": [],
                    }
                )
                return summary
            files, total_size, truncated = self._scan_artifact_directory(resolved)
            files.sort(key=lambda item: item[1].st_mtime, reverse=True)
            summary.update(
                {
                    "kind": "directory",
                    "file_count": len(files),
                    "total_size": total_size,
                    "scan_truncated": truncated,
                    "max_scan_files": self.OBJECT_ARTIFACT_MAX_SCAN_FILES,
                    "max_scan_depth": self.OBJECT_ARTIFACT_MAX_SCAN_DEPTH,
                    "latest_files": [
                        self._artifact_file_summary(item, stat=stat)
                        for item, stat in files[
                            : self.OBJECT_ARTIFACT_LATEST_FILE_LIMIT
                        ]
                    ],
                }
            )
            return summary
        except OSError as exc:
            summary.update(
                {
                    "kind": "error",
                    "file_count": 0,
                    "total_size": 0,
                    "latest_files": [],
                    "error": str(exc),
                }
            )
            return summary

    def _scan_artifact_directory(
        self, root: Path
    ) -> tuple[list[tuple[Path, Any]], int, bool]:
        files: list[tuple[Path, Any]] = []
        total_size = 0
        truncated = False
        pending: list[tuple[Path, int]] = [(root, 0)]
        while pending and len(files) < self.OBJECT_ARTIFACT_MAX_SCAN_FILES:
            directory, depth = pending.pop()
            try:
                children = sorted(directory.iterdir(), key=lambda item: item.name)
            except OSError:
                continue
            for child in children:
                if child.is_symlink():
                    continue
                try:
                    if child.is_file():
                        stat = child.stat()
                        total_size += stat.st_size
                        files.append((child, stat))
                        if len(files) >= self.OBJECT_ARTIFACT_MAX_SCAN_FILES:
                            truncated = True
                            break
                    elif child.is_dir() and depth < self.OBJECT_ARTIFACT_MAX_SCAN_DEPTH:
                        pending.append((child, depth + 1))
                except OSError:
                    continue
        if pending:
            truncated = True
        return files, total_size, truncated

    def _artifact_file_summary(self, path: Path, *, stat: Any) -> dict[str, Any]:
        return {
            "path": self._workspace_display_path(path),
            "name": path.name,
            "size": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        }

    def _workspace_display_path(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.root_path.resolve()).as_posix()
        except (OSError, ValueError):
            return path.as_posix()

    def _build_object_artifact_changes(
        self,
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> dict[str, Any]:
        before_objects: dict[str, dict[str, Any]] = {}
        for item in before.get("objects", []):
            if isinstance(item, dict) and isinstance(item.get("object_name"), str):
                before_objects[item["object_name"]] = item
        after_objects: dict[str, dict[str, Any]] = {}
        for item in after.get("objects", []):
            if isinstance(item, dict) and isinstance(item.get("object_name"), str):
                after_objects[item["object_name"]] = item
        changes: list[dict[str, Any]] = []
        for object_name in sorted(set(before_objects) | set(after_objects)):
            before_item = before_objects.get(object_name, {})
            after_item = after_objects.get(object_name, {})
            changed_fields: list[str] = []
            for field in ("object_found", "status", "installed"):
                if before_item.get(field) != after_item.get(field):
                    changed_fields.append(field)
            source_changes = self._build_artifact_source_changes(
                before_item.get("artifact_sources", {}),
                after_item.get("artifact_sources", {}),
            )
            if source_changes:
                changed_fields.append("artifact_sources")
            changes.append(
                {
                    "object_name": object_name,
                    "changed": bool(changed_fields),
                    "changed_fields": changed_fields,
                    "before_status": before_item.get("status"),
                    "after_status": after_item.get("status"),
                    "artifact_source_changes": source_changes,
                }
            )
        return {"objects": changes}

    def _build_artifact_source_changes(
        self,
        before_sources: Any,
        after_sources: Any,
    ) -> dict[str, Any]:
        if not isinstance(before_sources, dict):
            before_sources = {}
        if not isinstance(after_sources, dict):
            after_sources = {}
        changes: dict[str, Any] = {}
        for name in sorted(set(before_sources) | set(after_sources)):
            before_item = before_sources.get(name, {})
            after_item = after_sources.get(name, {})
            if not isinstance(before_item, dict):
                before_item = {}
            if not isinstance(after_item, dict):
                after_item = {}
            file_count_delta = int(after_item.get("file_count", 0) or 0) - int(
                before_item.get("file_count", 0) or 0
            )
            total_size_delta = int(after_item.get("total_size", 0) or 0) - int(
                before_item.get("total_size", 0) or 0
            )
            if (
                before_item.get("exists") != after_item.get("exists")
                or file_count_delta
                or total_size_delta
            ):
                changes[name] = {
                    "exists_before": before_item.get("exists"),
                    "exists_after": after_item.get("exists"),
                    "file_count_delta": file_count_delta,
                    "total_size_delta": total_size_delta,
                }
        return changes

    def _build_runtime_backend_capability(self, backend_name: str) -> dict[str, Any]:
        normalized = backend_name or "host"
        capabilities = {
            "process_spawn": normalized == "host",
            "tcp_bind": normalized == "host",
            "filesystem_write": normalized == "host",
            "environment_variables": normalized == "host",
            "core_limit_probe": _resource is not None
            and hasattr(_resource, "RLIMIT_CORE"),
        }
        limitations: list[str] = []
        if normalized != "host":
            limitations.append(f"runtime_backend_unsupported:{normalized}")
        if not capabilities["core_limit_probe"]:
            limitations.append("core_rlimit_unsupported")
        return {
            "name": normalized,
            "source": "workflow_service",
            "capabilities": capabilities,
            "limitations": limitations,
            "probed_at": datetime.now().isoformat(),
        }

    def _build_runtime_backend_requirements(self, profile: str) -> list[str]:
        if profile == "mysql_managed_instance":
            return [
                "process_spawn",
                "tcp_bind",
                "filesystem_write",
                "environment_variables",
            ]
        return []

    def _build_object_runtime_backend_summary(
        self,
        record: ManagedObjectRecord,
        *,
        last_preflight: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        config = record.config if isinstance(record.config, dict) else {}
        backend_name = str(config.get("runtime_backend", "host"))
        capability = self._build_runtime_backend_capability(backend_name)
        required = config.get("runtime_backend_requirements", [])
        if not isinstance(required, list):
            required = []
        required_capabilities = [str(item) for item in required if str(item)]
        capability_values = capability.get("capabilities", {})
        capabilities = capability_values if isinstance(capability_values, dict) else {}
        missing = [name for name in required_capabilities if not capabilities.get(name)]
        limitations = capability.get("limitations", [])
        unsupported = any(
            isinstance(item, str) and item.startswith("runtime_backend_unsupported:")
            for item in limitations
            if isinstance(limitations, list)
        )
        summary: dict[str, Any] = {
            "name": backend_name,
            "required_capabilities": required_capabilities,
            "capabilities": capabilities,
            "capability_status": "unsatisfied"
            if missing or unsupported
            else "satisfied",
            "missing_capabilities": missing,
            "limitations": limitations,
        }
        if last_preflight is not None:
            summary["last_preflight"] = last_preflight
        return summary

    def _build_problem_runtime_backend_context(
        self, object_refs: Any
    ) -> dict[str, Any]:
        if not isinstance(object_refs, list):
            return {}
        objects: list[dict[str, Any]] = []
        for raw_name in object_refs:
            if not isinstance(raw_name, str) or not raw_name:
                continue
            record = self.storage.get_object(raw_name)
            if record is None:
                objects.append(
                    {
                        "object_name": raw_name,
                        "object_found": False,
                    }
                )
                continue
            metadata = record.metadata if isinstance(record.metadata, dict) else {}
            runtime_backend = metadata.get("runtime_backend", {})
            if not isinstance(runtime_backend, dict) or not runtime_backend:
                runtime_backend = self._build_object_runtime_backend_summary(record)
            objects.append(
                {
                    "object_name": record.name,
                    "object_found": True,
                    "type_name": record.type_name,
                    "status": record.status,
                    "runtime_backend": runtime_backend,
                }
            )
        if not objects:
            return {}

        found_objects = [item for item in objects if item.get("object_found") is True]
        if not found_objects:
            status = "unknown"
        elif any(
            isinstance(item.get("runtime_backend"), dict)
            and item["runtime_backend"].get("capability_status") == "unsatisfied"
            for item in found_objects
        ):
            status = "unsatisfied"
        elif len(found_objects) != len(objects):
            status = "partial"
        else:
            status = "satisfied"
        return {
            "source": "object_refs",
            "status": status,
            "objects": objects,
        }

    def _build_problem_object_artifacts(
        self,
        record: ExecutionRecord,
        *,
        problem_type: str,
        object_refs: list[str],
    ) -> dict[str, Any]:
        object_artifacts = record.metadata.get("object_artifacts", {})
        if not isinstance(object_artifacts, dict):
            return {}
        selection = object_artifacts.get("selection", {})
        if not isinstance(selection, dict):
            selection = {}
        if (
            problem_type == "api_response"
            and selection.get("mode") == "all_objects_fallback"
        ):
            return {}
        filtered = self._filter_object_artifacts_for_problem(
            object_artifacts,
            object_refs=object_refs,
        )
        artifact_refs = record.metadata.get("artifacts", {})
        files = (
            artifact_refs.get("files", {}) if isinstance(artifact_refs, dict) else {}
        )
        if isinstance(files, dict) and isinstance(files.get("object_artifacts"), str):
            filtered["artifact_ref"] = files["object_artifacts"]
        return filtered

    def _filter_object_artifacts_for_problem(
        self,
        object_artifacts: dict[str, Any],
        *,
        object_refs: list[str],
    ) -> dict[str, Any]:
        ref_set = {name for name in object_refs if isinstance(name, str) and name}
        filtered = {
            "execution_id": object_artifacts.get("execution_id"),
            "selection": object_artifacts.get("selection", {}),
            "before": self._filter_object_artifact_snapshot(
                object_artifacts.get("before", {}),
                ref_set=ref_set,
            ),
            "after": self._filter_object_artifact_snapshot(
                object_artifacts.get("after", {}),
                ref_set=ref_set,
            ),
            "changes": self._filter_object_artifact_changes(
                object_artifacts.get("changes", {}),
                ref_set=ref_set,
            ),
        }
        return filtered

    def _filter_object_artifact_snapshot(
        self,
        snapshot: Any,
        *,
        ref_set: set[str],
    ) -> dict[str, Any]:
        if not isinstance(snapshot, dict):
            return {"captured_at": None, "objects": []}
        objects = snapshot.get("objects", [])
        if not isinstance(objects, list):
            objects = []
        if ref_set:
            objects = [
                item
                for item in objects
                if isinstance(item, dict) and item.get("object_name") in ref_set
            ]
        return {
            "captured_at": snapshot.get("captured_at"),
            "objects": objects,
        }

    def _filter_object_artifact_changes(
        self,
        changes: Any,
        *,
        ref_set: set[str],
    ) -> dict[str, Any]:
        if not isinstance(changes, dict):
            return {"objects": []}
        objects = changes.get("objects", [])
        if not isinstance(objects, list):
            objects = []
        if ref_set:
            objects = [
                item
                for item in objects
                if isinstance(item, dict) and item.get("object_name") in ref_set
            ]
        return {"objects": objects}

    def _build_execution_object_artifacts_summary(
        self,
        artifact_index: dict[str, Any],
    ) -> dict[str, Any]:
        files = artifact_index.get("files", {})
        if not isinstance(files, dict):
            return {
                "available": False,
                "reason": "artifact_files_unavailable",
            }
        artifact_ref = files.get("object_artifacts")
        if not isinstance(artifact_ref, str) or not artifact_ref:
            return {
                "available": False,
                "reason": "object_artifacts_not_registered",
            }
        try:
            object_artifacts = self.storage.read_artifact_file(artifact_ref)
        except (OSError, ValueError) as exc:
            return {
                "available": False,
                "artifact_ref": artifact_ref,
                "error": str(exc),
            }
        if not isinstance(object_artifacts, dict):
            return {
                "available": False,
                "artifact_ref": artifact_ref,
                "reason": "object_artifacts_unreadable",
            }
        return self._summarize_object_artifacts(
            object_artifacts,
            artifact_ref=artifact_ref,
        )

    def _summarize_object_artifacts(
        self,
        object_artifacts: dict[str, Any],
        *,
        artifact_ref: str | None = None,
    ) -> dict[str, Any]:
        before_objects = self._object_artifact_snapshot_by_name(
            object_artifacts.get("before", {})
        )
        after_objects = self._object_artifact_snapshot_by_name(
            object_artifacts.get("after", {})
        )
        change_objects = self._object_artifact_changes_by_name(
            object_artifacts.get("changes", {})
        )
        object_names = sorted(
            set(before_objects) | set(after_objects) | set(change_objects)
        )
        objects: list[dict[str, Any]] = []
        changed_count = 0
        for object_name in object_names[:10]:
            before_item = before_objects.get(object_name, {})
            after_item = after_objects.get(object_name, {})
            change_item = change_objects.get(object_name, {})
            status_changed = self._object_artifact_status_changed(
                before_item,
                after_item,
                change_item,
            )
            changed = self._object_artifact_changed(
                before_item,
                after_item,
                change_item,
            )
            if changed:
                changed_count += 1
            object_summary: dict[str, Any] = {
                "object_name": object_name,
                "object_found": after_item.get(
                    "object_found", before_item.get("object_found")
                ),
                "before_status": change_item.get(
                    "before_status", before_item.get("status")
                ),
                "after_status": change_item.get(
                    "after_status", after_item.get("status")
                ),
                "status_changed": status_changed,
                "changed": changed,
            }
            artifact_source_changes = change_item.get("artifact_source_changes", {})
            if isinstance(artifact_source_changes, dict) and artifact_source_changes:
                object_summary["artifact_source_changes"] = artifact_source_changes
            objects.append(object_summary)
        for object_name in object_names[10:]:
            if self._object_artifact_changed(
                before_objects.get(object_name, {}),
                after_objects.get(object_name, {}),
                change_objects.get(object_name, {}),
            ):
                changed_count += 1
        summary: dict[str, Any] = {
            "available": True,
            "selection": object_artifacts.get("selection", {}),
            "object_count": len(object_names),
            "changed_object_count": changed_count,
            "objects": objects,
        }
        if artifact_ref is not None:
            summary["artifact_ref"] = artifact_ref
        execution_id = object_artifacts.get("execution_id")
        if isinstance(execution_id, str) and execution_id:
            summary["execution_id"] = execution_id
        return summary

    def _object_artifact_snapshot_by_name(
        self,
        snapshot: Any,
    ) -> dict[str, dict[str, Any]]:
        return self._object_artifacts_by_name(snapshot)

    def _object_artifact_changes_by_name(
        self,
        changes: Any,
    ) -> dict[str, dict[str, Any]]:
        return self._object_artifacts_by_name(changes)

    def _object_artifacts_by_name(
        self,
        payload: Any,
    ) -> dict[str, dict[str, Any]]:
        if not isinstance(payload, dict):
            return {}
        objects = payload.get("objects", [])
        if not isinstance(objects, list):
            return {}
        by_name: dict[str, dict[str, Any]] = {}
        for item in objects:
            if not isinstance(item, dict):
                continue
            object_name = item.get("object_name")
            if isinstance(object_name, str) and object_name:
                by_name[object_name] = item
        return by_name

    def _object_artifact_status_changed(
        self,
        before_item: dict[str, Any],
        after_item: dict[str, Any],
        change_item: dict[str, Any],
    ) -> bool:
        changed_fields = change_item.get("changed_fields", [])
        if change_item.get("changed") and isinstance(changed_fields, list):
            return "status" in changed_fields
        if "changed" not in change_item:
            return before_item.get("status") != after_item.get("status")
        return False

    def _object_artifact_changed(
        self,
        before_item: dict[str, Any],
        after_item: dict[str, Any],
        change_item: dict[str, Any],
    ) -> bool:
        if "changed" in change_item:
            return bool(change_item.get("changed"))
        return self._object_artifact_status_changed(
            before_item,
            after_item,
            change_item,
        )

    def _build_runtime_backend_preflight_summary(
        self,
        *,
        success: bool,
        message: str,
    ) -> dict[str, Any] | None:
        reason = ""
        message_lower = message.lower()
        if (
            "does not permit binding" in message_lower
            or "operation not permitted" in message_lower
        ):
            reason = "tcp_bind_denied"
        elif "cannot prepare a managed mysql service" in message_lower:
            reason = "tcp_bind_unavailable"
        elif "runtime backend" in message_lower and "supports only" in message_lower:
            reason = "runtime_backend_unsupported"
        if not success and not reason:
            return None
        return {
            "status": "success" if success else "failed",
            "message": message,
            "failure_reason": reason,
            "checked_at": datetime.now().isoformat(),
        }

    def _workspace_dump_dir(self) -> Path:
        return self.root_path / "dumps"

    def _build_environment_crash_capture_capability(
        self,
        dump_dir: str | Path | None = None,
    ) -> dict[str, Any]:
        resolved_dump_dir = Path(dump_dir or self._workspace_dump_dir()).resolve()
        core_supported = _resource is not None and hasattr(_resource, "RLIMIT_CORE")
        current_limit = None
        limitations: list[str] = []
        core_enabled = False
        if core_supported:
            try:
                soft, hard = _resource.getrlimit(_resource.RLIMIT_CORE)
                current_limit = {
                    "soft": self._serialize_core_limit_value(soft),
                    "hard": self._serialize_core_limit_value(hard),
                }
                core_enabled = soft != 0
                if hard == 0:
                    limitations.append("process_core_hard_limit_disabled")
            except (OSError, ValueError) as exc:
                limitations.append(f"core_limit_probe_failed:{exc}")
        else:
            limitations.append("core_rlimit_unsupported")
        return {
            "core_supported": core_supported,
            "core_enabled": core_enabled,
            "dump_dir": str(resolved_dump_dir),
            "limitations": limitations,
            "enable_attempt": {
                "attempted": False,
                "status": "pending",
                "strategy": "process_rlimit_core",
                "failure_reason": "",
            },
            "current_limit": current_limit,
        }

    def _build_object_crash_capture_capability(
        self,
        dump_dir: str | Path | None = None,
    ) -> dict[str, Any]:
        capability = self._build_environment_crash_capture_capability(
            dump_dir=dump_dir or self._workspace_dump_dir()
        )
        capability["source"] = "object_runtime_wrapper"
        return capability

    def _merge_object_crash_capture_capability(
        self,
        record: ManagedObjectRecord,
        existing: Any,
    ) -> dict[str, Any]:
        if isinstance(existing, dict) and existing.get("dump_dir"):
            capability = existing.copy()
        else:
            managed_instance = (
                record.config.get("managed_instance", {})
                if isinstance(record.config, dict)
                else {}
            )
            dump_dir = None
            if isinstance(managed_instance, dict):
                dump_dir = managed_instance.get("dump_dir")
            capability = self._build_object_crash_capture_capability(dump_dir=dump_dir)
        enable_attempt = capability.get("enable_attempt")
        if not isinstance(enable_attempt, dict):
            capability["enable_attempt"] = {
                "attempted": False,
                "status": "pending",
                "strategy": "process_rlimit_core",
                "failure_reason": "",
            }
        return capability

    def _attempt_object_crash_capture_enable(
        self,
        capability: dict[str, Any],
    ) -> dict[str, Any]:
        updated = capability.copy()
        dump_dir = Path(str(updated.get("dump_dir") or self._workspace_dump_dir()))
        enable_attempt = dict(updated.get("enable_attempt", {}))
        enable_attempt.update(
            {
                "attempted": True,
                "strategy": "process_rlimit_core",
                "failure_reason": "",
                "attempted_at": datetime.now().isoformat(),
            }
        )

        try:
            dump_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            updated["core_enabled"] = False
            limitations = list(updated.get("limitations", []))
            limitations.append("dump_dir_unavailable")
            updated["limitations"] = limitations
            enable_attempt["status"] = "failed"
            enable_attempt["failure_reason"] = str(exc)
            updated["enable_attempt"] = enable_attempt
            return updated

        if _resource is None or not updated.get("core_supported", False):
            enable_attempt["status"] = "failed"
            enable_attempt["failure_reason"] = "core_rlimit_unsupported"
            updated["enable_attempt"] = enable_attempt
            return updated

        try:
            soft, hard = _resource.getrlimit(_resource.RLIMIT_CORE)
            if soft == 0:
                if hard == 0:
                    raise RuntimeError("process_core_hard_limit_disabled")
                _resource.setrlimit(_resource.RLIMIT_CORE, (hard, hard))
                soft, hard = _resource.getrlimit(_resource.RLIMIT_CORE)
            updated["current_limit"] = {
                "soft": self._serialize_core_limit_value(soft),
                "hard": self._serialize_core_limit_value(hard),
            }
            updated["core_enabled"] = soft != 0
            enable_attempt["status"] = "success" if soft != 0 else "failed"
            if soft == 0:
                enable_attempt["failure_reason"] = "process_core_soft_limit_disabled"
        except (OSError, ValueError, RuntimeError) as exc:
            updated["core_enabled"] = False
            limitations = list(updated.get("limitations", []))
            limitations.append("core_enable_attempt_failed")
            updated["limitations"] = limitations
            enable_attempt["status"] = "failed"
            enable_attempt["failure_reason"] = str(exc)

        updated["enable_attempt"] = enable_attempt
        return updated

    def _serialize_core_limit_value(self, value: int) -> str | int:
        if _resource is not None and value == _resource.RLIM_INFINITY:
            return "unlimited"
        return value

    # ── runtime preflight checks ────────────────────────────────────────

    _PREFLIGHT_SUPPORTED_TYPES = {"database_server"}

    def _supports_runtime_preflight(self, record: ManagedObjectRecord) -> bool:
        if record.type_name not in self._PREFLIGHT_SUPPORTED_TYPES:
            return False
        config = record.config if isinstance(record.config, dict) else {}
        if str(config.get("db_type", "")).lower() != "mysql":
            return False
        managed_instance = config.get("managed_instance", {})
        if not isinstance(managed_instance, dict) or not managed_instance:
            return False
        return True

    def _build_object_runtime_preflight(
        self,
        record: ManagedObjectRecord,
        *,
        scope: str = "start",
    ) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []
        checks.append(self._runtime_preflight_check_object_installation(record))
        checks.append(self._runtime_preflight_check_runtime_backend(record))
        checks.append(self._runtime_preflight_check_workspace_boundary(record))
        checks.append(self._runtime_preflight_check_managed_paths(record))
        checks.append(self._runtime_preflight_check_pid_state(record))
        checks.append(self._runtime_preflight_check_port_bind(record))
        checks.append(self._runtime_preflight_check_dependency_assets(record))
        summary = self._summarize_runtime_preflight_checks(checks)
        return {
            "object_name": record.name,
            "object_type": record.type_name,
            "scope": scope,
            "status": summary["status"],
            "checked_at": datetime.now().isoformat(),
            "can_start": summary["required_failed"] == 0,
            "can_run": summary["required_failed"] == 0,
            "checks": checks,
            "summary": summary,
        }

    def _runtime_preflight_check_object_installation(
        self,
        record: ManagedObjectRecord,
    ) -> dict[str, Any]:
        if not record.installed:
            return {
                "code": "object_installation",
                "status": "failed",
                "required": True,
                "message": "object is not installed",
                "details": {},
            }
        if record.status == OBJECT_STATUS_INSTALL_FAILED_PRESERVED:
            return {
                "code": "object_installation",
                "status": "failed",
                "required": True,
                "message": "object installation failed and state is preserved",
                "details": {"status": record.status},
            }
        if record.status == OBJECT_STATUS_START_FAILED_PRESERVED:
            return {
                "code": "object_installation",
                "status": "warning",
                "required": False,
                "message": "object start previously failed; consider clear/reset before retrying",
                "details": {"status": record.status},
            }
        return {
            "code": "object_installation",
            "status": "passed",
            "required": True,
            "message": "object is installed and available",
            "details": {},
        }

    def _runtime_preflight_check_runtime_backend(
        self,
        record: ManagedObjectRecord,
    ) -> dict[str, Any]:
        try:
            summary = self._build_object_runtime_backend_summary(record)
        except Exception as exc:
            return {
                "code": "runtime_backend_capabilities",
                "status": "failed",
                "required": True,
                "message": f"failed to build runtime backend summary: {exc}",
                "details": {},
            }
        capability_status = summary.get("capability_status", "")
        if capability_status == "unsatisfied":
            return {
                "code": "runtime_backend_capabilities",
                "status": "failed",
                "required": True,
                "message": "runtime backend does not satisfy required capabilities",
                "details": {
                    "backend": summary.get("name"),
                    "missing_capabilities": summary.get("missing_capabilities", []),
                },
            }
        last_preflight = summary.get("last_preflight")
        if (
            isinstance(last_preflight, dict)
            and last_preflight.get("status") == "failed"
        ):
            failure_reason = last_preflight.get("failure_reason", "")
            if failure_reason in {"tcp_bind_denied", "runtime_backend_unsupported"}:
                return {
                    "code": "runtime_backend_capabilities",
                    "status": "failed",
                    "required": True,
                    "message": f"last runtime preflight failed: {failure_reason}",
                    "details": {"last_preflight": last_preflight},
                }
            return {
                "code": "runtime_backend_capabilities",
                "status": "warning",
                "required": False,
                "message": f"last runtime preflight failed: {failure_reason}",
                "details": {"last_preflight": last_preflight},
            }
        return {
            "code": "runtime_backend_capabilities",
            "status": "passed",
            "required": True,
            "message": "runtime backend satisfies required capabilities",
            "details": {},
        }

    def _runtime_preflight_check_workspace_boundary(
        self,
        record: ManagedObjectRecord,
    ) -> dict[str, Any]:
        config = record.config if isinstance(record.config, dict) else {}
        try:
            workspace_path = (
                Path(str(config.get("workspace_path", self.root_path)))
                .expanduser()
                .resolve()
            )
        except (OSError, ValueError) as exc:
            return {
                "code": "workspace_boundary",
                "status": "failed",
                "required": True,
                "message": f"workspace path could not be resolved: {exc}",
                "details": {
                    "workspace_path": str(config.get("workspace_path", "")),
                },
            }
        managed_instance = config.get("managed_instance", {})
        if not isinstance(managed_instance, dict):
            managed_instance = {}
        path_sources = {
            "workspace_path": str(config.get("workspace_path", "")),
            "config_file": str(config.get("config_file", "")),
            "log_file": str(config.get("log_file", "")),
            "pid_file": str(config.get("pid_file", "")),
            "staged_package_path": str(config.get("staged_package_path", "")),
        }
        for key, value in managed_instance.items():
            if isinstance(value, str) and value:
                path_sources[f"managed_instance.{key}"] = value
        violations: list[str] = []
        for label, raw_path in path_sources.items():
            if not raw_path:
                continue
            try:
                if not self._path_within_workspace(workspace_path, Path(raw_path)):
                    violations.append(label)
            except (OSError, ValueError):
                violations.append(f"{label}:unresolvable")
        if violations:
            return {
                "code": "workspace_boundary",
                "status": "failed",
                "required": True,
                "message": f"critical paths escape workspace: {', '.join(violations)}",
                "details": {
                    "workspace_path": str(workspace_path),
                    "violations": violations,
                },
            }
        return {
            "code": "workspace_boundary",
            "status": "passed",
            "required": True,
            "message": "all critical paths are within workspace",
            "details": {},
        }

    def _runtime_preflight_check_managed_paths(
        self,
        record: ManagedObjectRecord,
    ) -> dict[str, Any]:
        config = record.config if isinstance(record.config, dict) else {}
        managed_instance = config.get("managed_instance", {})
        if not isinstance(managed_instance, dict):
            managed_instance = {}
        required_dirs = [
            "instance_root",
            "install_dir",
            "data_dir",
            "config_dir",
            "run_dir",
            "log_dir",
        ]
        missing_required: list[str] = []
        missing_optional: list[str] = []
        unwritable: list[str] = []
        for dir_key in required_dirs:
            raw = managed_instance.get(dir_key, "")
            if not raw:
                continue
            try:
                path = Path(raw).expanduser().resolve()
                if path.exists():
                    if not os.access(path, os.W_OK):
                        unwritable.append(dir_key)
                else:
                    parent = path.parent
                    if parent.exists() and os.access(parent, os.W_OK):
                        missing_optional.append(dir_key)
                    else:
                        missing_required.append(dir_key)
            except (OSError, ValueError):
                missing_required.append(f"{dir_key}:unresolvable")
        config_file = str(config.get("config_file", ""))
        if config_file:
            try:
                if not Path(config_file).expanduser().resolve().exists():
                    missing_required.append("config_file")
            except (OSError, ValueError):
                missing_required.append("config_file:unresolvable")
        problems = missing_required + unwritable
        if problems:
            return {
                "code": "managed_paths",
                "status": "failed",
                "required": True,
                "message": f"required paths missing or unwritable: {', '.join(problems)}",
                "details": {
                    "missing_required": missing_required,
                    "missing_optional": missing_optional,
                    "unwritable": unwritable,
                },
            }
        if missing_optional:
            return {
                "code": "managed_paths",
                "status": "warning",
                "required": False,
                "message": f"some directories will be created at start: {', '.join(missing_optional)}",
                "details": {"missing_optional": missing_optional},
            }
        return {
            "code": "managed_paths",
            "status": "passed",
            "required": True,
            "message": "all managed paths are available",
            "details": {},
        }

    def _runtime_preflight_check_pid_state(
        self,
        record: ManagedObjectRecord,
    ) -> dict[str, Any]:
        config = record.config if isinstance(record.config, dict) else {}
        pid_file_raw = str(config.get("pid_file", ""))
        if not pid_file_raw:
            return {
                "code": "pid_state",
                "status": "passed",
                "required": False,
                "message": "no pid file configured",
                "details": {},
            }
        try:
            pid_file = Path(pid_file_raw).expanduser().resolve()
        except (OSError, ValueError):
            return {
                "code": "pid_state",
                "status": "warning",
                "required": False,
                "message": "pid file path could not be resolved",
                "details": {"pid_file": pid_file_raw},
            }
        if not pid_file.exists():
            return {
                "code": "pid_state",
                "status": "passed",
                "required": False,
                "message": "no pid file present",
                "details": {},
            }
        pid = self._read_pid_file(pid_file)
        if pid is None:
            return {
                "code": "pid_state",
                "status": "warning",
                "required": False,
                "message": "pid file exists but could not be read",
                "details": {"pid_file": str(pid_file)},
            }
        if self._is_pid_running(pid):
            if record.status == OBJECT_STATUS_RUNNING:
                return {
                    "code": "pid_state",
                    "status": "warning",
                    "required": False,
                    "message": f"pid {pid} is running and object status is running",
                    "details": {"pid": pid},
                }
            return {
                "code": "pid_state",
                "status": "failed",
                "required": True,
                "message": f"pid {pid} is running but object status is '{record.status}'; residual process detected",
                "details": {"pid": pid, "object_status": record.status},
            }
        return {
            "code": "pid_state",
            "status": "warning",
            "required": False,
            "message": f"stale pid file references non-running pid {pid}",
            "details": {"pid": pid},
        }

    def _runtime_preflight_check_port_bind(
        self,
        record: ManagedObjectRecord,
    ) -> dict[str, Any]:
        config = record.config if isinstance(record.config, dict) else {}
        host = str(config.get("server_host", "127.0.0.1"))
        port = self._coerce_mysql_port(config.get("server_port", config.get("port")))
        if port <= 0:
            return {
                "code": "port_bind",
                "status": "failed",
                "required": True,
                "message": "port is missing or invalid",
                "details": {"port": port},
            }
        # running 对象用 TCP connect 验证端口可达性
        if record.status == OBJECT_STATUS_RUNNING:
            try:
                reachable = self._is_host_port_reachable(host, port)
            except Exception as exc:
                return {
                    "code": "port_bind",
                    "status": "warning",
                    "required": False,
                    "message": f"port reachability check failed: {exc}",
                    "details": {"host": host, "port": port},
                }
            if reachable:
                return {
                    "code": "port_bind",
                    "status": "passed",
                    "required": True,
                    "message": f"port {host}:{port} is reachable (object is running)",
                    "details": {"host": host, "port": port},
                }
            return {
                "code": "port_bind",
                "status": "warning",
                "required": False,
                "message": f"port {host}:{port} is not reachable but object status is running",
                "details": {"host": host, "port": port},
            }
        # 非 running 对象用 bind probe 检测端口是否可被当前进程绑定
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                probe.bind((host, port))
        except PermissionError as exc:
            return {
                "code": "port_bind",
                "status": "failed",
                "required": True,
                "reason": "bind_denied",
                "message": f"runtime backend does not permit binding {host}:{port}: {exc}",
                "details": {"host": host, "port": port},
            }
        except OSError as exc:
            return {
                "code": "port_bind",
                "status": "failed",
                "required": True,
                "reason": "bind_unavailable",
                "message": f"port {host}:{port} bind failed: {exc}",
                "details": {"host": host, "port": port},
            }
        return {
            "code": "port_bind",
            "status": "passed",
            "required": True,
            "message": f"port {host}:{port} is available for binding",
            "details": {"host": host, "port": port},
        }

    def _runtime_preflight_check_dependency_assets(
        self,
        record: ManagedObjectRecord,
    ) -> dict[str, Any]:
        config = record.config if isinstance(record.config, dict) else {}
        missing_required: list[str] = []
        missing_optional: list[str] = []
        schema_warnings: list[str] = []
        dependency_assets = config.get("dependency_assets", [])
        if isinstance(dependency_assets, list):
            for asset in dependency_assets:
                if not isinstance(asset, dict):
                    continue
                asset_path = str(asset.get("path", ""))
                if not asset_path:
                    continue
                is_required = bool(asset.get("required", True))
                try:
                    if not Path(asset_path).expanduser().resolve().exists():
                        if is_required:
                            missing_required.append(asset_path)
                        else:
                            missing_optional.append(asset_path)
                except (OSError, ValueError):
                    if is_required:
                        missing_required.append(f"{asset_path}:unresolvable")
                    else:
                        missing_optional.append(f"{asset_path}:unresolvable")
        runtime_library_paths = config.get("runtime_library_paths", [])
        if isinstance(runtime_library_paths, list):
            for lib_path in runtime_library_paths:
                if not isinstance(lib_path, str) or not lib_path:
                    continue
                try:
                    if not Path(lib_path).expanduser().resolve().exists():
                        missing_required.append(lib_path)
                except (OSError, ValueError):
                    missing_required.append(f"{lib_path}:unresolvable")
        dependency_requirements = config.get("dependency_requirements")
        if dependency_requirements is not None and not isinstance(
            dependency_requirements, dict
        ):
            schema_warnings.append(
                f"dependency_requirements is {type(dependency_requirements).__name__}, expected dict"
            )
        details: dict[str, Any] = {}
        if missing_required:
            details["missing_required"] = missing_required
        if missing_optional:
            details["missing_optional"] = missing_optional
        if schema_warnings:
            details["schema_warnings"] = schema_warnings
        if isinstance(dependency_requirements, dict) and dependency_requirements:
            details["dependency_requirements_keys"] = sorted(
                str(k) for k in dependency_requirements
            )
        if missing_required:
            return {
                "code": "dependency_assets",
                "status": "failed",
                "required": True,
                "message": f"required dependency assets missing: {', '.join(missing_required)}",
                "details": details,
            }
        if schema_warnings or missing_optional:
            warnings_combined = schema_warnings + [
                f"optional asset missing: {p}" for p in missing_optional
            ]
            return {
                "code": "dependency_assets",
                "status": "warning",
                "required": False,
                "message": "; ".join(warnings_combined),
                "details": details,
            }
        return {
            "code": "dependency_assets",
            "status": "passed",
            "required": True,
            "message": "all dependency assets are available",
            "details": details,
        }

    def _summarize_runtime_preflight_checks(
        self,
        checks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        passed = sum(1 for c in checks if c.get("status") == "passed")
        warning = sum(1 for c in checks if c.get("status") == "warning")
        failed = sum(1 for c in checks if c.get("status") == "failed")
        required_failed = sum(
            1
            for c in checks
            if c.get("status") == "failed" and c.get("required", False)
        )
        if required_failed > 0:
            status = "failed"
        elif warning > 0:
            status = "warning"
        else:
            status = "passed"
        return {
            "status": status,
            "passed": passed,
            "warning": warning,
            "failed": failed,
            "required_failed": required_failed,
        }

    _DEPENDENCY_CONFIGURATION_CHECKS = {
        "object_installation",
        "runtime_backend_capabilities",
        "workspace_boundary",
        "managed_paths",
        "dependency_assets",
    }

    def _classify_preflight_problem_type(
        self,
        checks: list[dict[str, Any]],
    ) -> str:
        for check in checks:
            if not (check.get("status") == "failed" and check.get("required", False)):
                continue
            code = check.get("code")
            if code in self._DEPENDENCY_CONFIGURATION_CHECKS:
                return "dependency_configuration"
            # port_bind PermissionError 属于 backend capability 问题
            if code == "port_bind" and check.get("reason") == "bind_denied":
                return "dependency_configuration"
        return "dependency_object"

    def check_object_readiness(
        self,
        name: str,
        *,
        scope: str = "start",
    ) -> dict[str, Any]:
        record = self.storage.get_object(name)
        if record is None:
            return self._not_found_result("object", name)
        if not self._supports_runtime_preflight(record):
            return self._operation_result(
                success=False,
                status="unavailable",
                message=f"runtime preflight is not available for object type '{record.type_name}'",
                error_code="object_type_not_supported",
            )
        preflight = self._build_object_runtime_preflight(record, scope=scope)
        metadata = record.metadata if isinstance(record.metadata, dict) else {}
        metadata.setdefault("runtime_preflight", {})
        metadata["runtime_preflight"]["last_check"] = preflight
        record.metadata = metadata
        record.updated_at = datetime.now().isoformat()
        self.storage.upsert_object(record)
        success = preflight["status"] != "failed"
        return self._operation_result(
            success=success,
            status=preflight["status"],
            message=f"Object '{name}' preflight: {preflight['status']}",
            data=preflight,
            runtime_preflight=preflight,
            error_code=None if success else "object_preflight_failed",
        )

    def _collect_object_runtime_snapshot(
        self,
        obj: Any,
        existing: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        snapshot = dict(existing or {})
        snapshot.update(
            {
                "status": getattr(obj, "status", snapshot.get("status")),
                "installed": getattr(obj, "installed", snapshot.get("installed")),
            }
        )
        if hasattr(obj, "get_status"):
            try:
                snapshot["details"] = obj.get_status()
            except Exception as exc:
                snapshot["details_error"] = str(exc)
        if hasattr(obj, "get_endpoint"):
            endpoint = obj.get_endpoint()
            if endpoint:
                snapshot["endpoint"] = endpoint
        if hasattr(obj, "get_server_endpoint"):
            endpoint = obj.get_server_endpoint()
            if endpoint:
                snapshot["server_endpoint"] = endpoint
        return snapshot

    def _materialize_tool(self, record: ToolRecord) -> Any:
        manager = self._get_tool_manager()
        manager.install(record.name, record.config)
        materialized = manager.tools[record.name]
        materialized.installed = record.installed
        materialized.status = record.status
        return materialized

    def _execute_case_with_bindings(
        self,
        case_manager: CaseManager,
        case_id: str,
        params: dict[str, Any] | None = None,
    ) -> tuple[TestCaseResult, dict[str, Any] | None]:
        resolved_params, case_definition, failure = self._prepare_case_execution(
            case_manager,
            case_id,
            params=params,
        )
        if failure is not None:
            return failure, case_definition
        return case_manager.run_case(case_id, params=resolved_params), case_definition

    def _execute_case_with_artifact_capture(
        self,
        case_manager: CaseManager,
        case_id: str,
        params: dict[str, Any] | None = None,
    ) -> tuple[
        TestCaseResult,
        dict[str, Any] | None,
        dict[str, Any],
        dict[str, Any],
        dict[str, Any] | None,
    ]:
        resolved_params, case_definition, failure = self._prepare_case_execution(
            case_manager,
            case_id,
            params=params,
        )
        object_artifacts_before = self._capture_object_artifacts_before(case_definition)
        crash_snapshot_before = self._capture_workspace_crash_dump_snapshot(
            case_definition
        )
        data_state_snapshot_before = self._capture_data_state_snapshot(
            case_definition, phase="before"
        )
        if failure is not None:
            result = failure
        else:
            result = case_manager.run_case(case_id, params=resolved_params)
        return (
            result,
            case_definition,
            crash_snapshot_before,
            object_artifacts_before,
            data_state_snapshot_before,
        )

    def _prepare_case_execution(
        self,
        case_manager: CaseManager,
        case_id: str,
        params: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None, TestCaseResult | None]:
        resolved_params, failure = self._resolve_case_runtime_params(
            case_manager,
            case_id,
            params=params,
        )
        case_definition = self._build_case_execution_definition(
            case_manager,
            case_id,
            resolved_params,
        )
        if failure is not None:
            return resolved_params, case_definition, failure
        return resolved_params, case_definition, None

    def _resolve_case_runtime_params(
        self,
        case_manager: CaseManager,
        case_id: str,
        params: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, TestCaseResult | None]:
        resolved_params = params.copy() if params else {}
        case_definition = case_manager.get_case(case_id)
        if not isinstance(case_definition, dict):
            return resolved_params or None, None
        case_payload = self._unwrap_case_definition(case_definition)
        if case_payload.get("type") != "database":
            return resolved_params or None, None

        object_name = resolved_params.get(
            "object_name", case_payload.get("object_name")
        )
        if not isinstance(object_name, str) or not object_name:
            return resolved_params or None, None

        binding_params, failure_message = self._resolve_database_object_binding(
            case_id,
            case_payload,
            object_name,
        )
        if failure_message is not None:
            return resolved_params or None, self._build_case_preflight_error(
                case_id,
                failure_message,
            )

        for key, value in binding_params.items():
            if key in case_payload or key in resolved_params:
                continue
            resolved_params[key] = value
        resolved_params.setdefault("object_name", object_name)
        return resolved_params, None

    def _resolve_database_object_binding(
        self,
        case_id: str,
        case_payload: dict[str, Any],
        object_name: str,
    ) -> tuple[dict[str, Any], str | None]:
        record = self.storage.get_object(object_name)
        if record is None:
            message = (
                f"Bound database object '{object_name}' does not exist for case "
                f"'{case_id}'"
            )
            self._record_environment_dependency_problem(
                problem_type="dependency_object",
                summary=f"Database case '{case_id}' references a missing object",
                details={
                    "phase": "case_binding",
                    "case_id": case_id,
                    "case": case_payload,
                    "object_name": object_name,
                    "message": message,
                },
                recovery={
                    "supported": False,
                    "mode": "minimal_environment_recovery",
                    "action": "install_object",
                    "object_name": object_name,
                    "required_state": "running",
                },
                object_refs=[object_name],
            )
            return {}, message

        if record.status != "running":
            message = (
                f"Bound database object '{object_name}' is not running "
                f"(status: {record.status})"
            )
            self._record_environment_dependency_problem(
                problem_type="dependency_object",
                summary=f"Database case '{case_id}' references an unavailable object",
                details={
                    "phase": "case_binding",
                    "case_id": case_id,
                    "case": case_payload,
                    "object": record.to_dict(),
                    "message": message,
                },
                recovery={
                    "supported": False,
                    "mode": "minimal_environment_recovery",
                    "action": "start_object",
                    "object_name": object_name,
                    "required_state": "running",
                },
                object_refs=[object_name],
            )
            return {}, message

        config = record.config if isinstance(record.config, dict) else {}
        runtime = record.metadata.get("runtime", {})
        runtime_details = (
            runtime.get("details", {}) if isinstance(runtime, dict) else {}
        )
        if not isinstance(runtime_details, dict):
            runtime_details = {}
        db_type = str(
            config.get("db_type", runtime_details.get("db_type", "mysql"))
        ).lower()

        if db_type == "mysql":
            scenario = config.get("scenario", {})
            mysql_config = config.get("mysql_config", {})
            if not isinstance(scenario, dict):
                scenario = {}
            if not isinstance(mysql_config, dict):
                mysql_config = {}
            binding = {
                "db_type": "mysql",
                "host": str(config.get("server_host", "127.0.0.1")),
                "port": int(
                    config.get(
                        "server_port",
                        self.DEFAULT_MANAGED_MYSQL_PORT,
                    )
                ),
                "username": str(mysql_config.get("username", "root")),
                "password": str(mysql_config.get("password", "")),
                "bound_object": {
                    "name": object_name,
                    "type_name": record.type_name,
                    "db_type": db_type,
                },
            }
            database_name = str(mysql_config.get("database", "")).strip()
            if database_name:
                binding["database"] = database_name
            return (binding, None)

        if db_type == "sqlite":
            database_path = config.get("database")
            if isinstance(database_path, str) and database_path:
                return (
                    {
                        "db_type": "sqlite",
                        "database": database_path,
                        "bound_object": {
                            "name": object_name,
                            "type_name": record.type_name,
                            "db_type": db_type,
                        },
                    },
                    None,
                )

        message = (
            f"Bound object '{object_name}' is not a supported database test target "
            f"(db_type: {db_type})"
        )
        self._record_environment_dependency_problem(
            problem_type="dependency_object",
            summary=f"Database case '{case_id}' references an unsupported object",
            details={
                "phase": "case_binding",
                "case_id": case_id,
                "case": case_payload,
                "object": record.to_dict(),
                "message": message,
            },
            recovery={
                "supported": False,
                "mode": "minimal_environment_recovery",
                "action": "rebind_case_object",
                "object_name": object_name,
                "required_state": "supported_database_target",
            },
            object_refs=[object_name],
        )
        return {}, message

    def _build_case_preflight_error(
        self,
        case_id: str,
        message: str,
    ) -> TestCaseResult:
        result = TestCaseResult(case_id)
        result.status = "error"
        result.error_message = message
        result.end_time = datetime.now()
        result.duration = (result.end_time - result.start_time).total_seconds()
        return result

    def _build_case_execution_definition(
        self,
        case_manager: CaseManager,
        case_id: str,
        params: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        case_definition = case_manager.get_case(case_id)
        if not isinstance(case_definition, dict):
            return None
        if not params:
            return case_definition
        merged_data = case_manager._merge_params(  # noqa: SLF001
            self._unwrap_case_definition(case_definition),
            params,
        )
        merged_definition = dict(case_definition)
        merged_definition["data"] = merged_data
        return merged_definition

    def _persist_execution(
        self,
        case_id: str,
        result: TestCaseResult,
        case_manager: CaseManager,
        case_definition_override: dict[str, Any] | None = None,
        crash_snapshot_before: dict[str, Any] | None = None,
        object_artifacts_before: dict[str, Any] | None = None,
        data_state_snapshot_before: dict[str, Any] | None = None,
    ) -> ExecutionRecord:
        execution_id = f"{case_id}_{uuid.uuid4().hex[:12]}"
        environment = self.get_environment_status()
        objects = self.list_objects()
        case_definition = case_definition_override or case_manager.get_case(case_id)
        crash_snapshot_after = self._capture_workspace_crash_dump_snapshot(
            case_definition
        )
        object_artifacts = self._build_object_artifacts_record(
            execution_id=execution_id,
            case_definition=case_definition,
            before_capture=object_artifacts_before,
        )
        data_state_artifacts = self._build_data_state_artifacts_record(
            execution_id=execution_id,
            case_definition=case_definition,
            before_capture=data_state_snapshot_before,
        )
        result_payload = self._result_payload(result)
        record = ExecutionRecord(
            execution_id=execution_id,
            case_id=case_id,
            status=result.status,
            duration=result.duration,
            start_time=result.start_time.isoformat(),
            end_time=result.end_time.isoformat(),
            error_message=result.error_message,
            output=result.output,
            metadata={
                "environment": environment,
                "objects": objects,
                "case": case_definition,
                "crash_capture": {
                    "before": crash_snapshot_before or {},
                    "after": crash_snapshot_after,
                    "new_dump_refs": self._detect_new_crash_dump_refs(
                        crash_snapshot_before or {},
                        crash_snapshot_after,
                    ),
                },
                "object_artifacts": object_artifacts,
                "data_state_artifacts": data_state_artifacts,
            },
        )
        artifacts = self.storage.save_execution_artifacts(
            execution_id,
            environment=environment,
            objects=objects,
            case=case_definition,
            result=result_payload,
            output=result.output,
            object_artifacts=object_artifacts,
            data_state_artifacts=data_state_artifacts,
        )
        record.metadata["artifacts"] = artifacts
        artifact_index = self.storage.save_execution_artifact_record(record)
        artifact_index.setdefault("indexes", {})
        artifact_index["indexes"]["log_index"] = artifact_index["indexes"].get(
            "log_index",
            str(self.storage.artifacts_dir / execution_id / "logs" / "log_index.json"),
        )
        artifact_index["log_index"] = (
            self.storage.get_execution_log_index(execution_id) or {}
        )
        record.metadata["artifacts"] = artifact_index
        record = self.storage.save_execution(record)
        self._preserve_problem_for_execution(record)
        return record

    def _execution_to_result(self, record: ExecutionRecord) -> TestCaseResult:
        result = TestCaseResult(record.case_id)
        result.status = record.status
        result.duration = record.duration
        result.start_time = datetime.fromisoformat(record.start_time)
        result.end_time = datetime.fromisoformat(record.end_time)
        result.error_message = record.error_message
        result.output = record.output or ""
        return result

    def _result_payload(self, result: TestCaseResult) -> dict[str, Any]:
        return {
            "case_id": result.case_id,
            "status": result.status,
            "success": result.success,
            "duration": result.duration,
            "error": result.error_message,
            "output": result.output,
        }

    def _summarize_results(self, results: list[dict[str, Any]]) -> dict[str, Any]:
        passed = sum(1 for result in results if result["success"])
        failed = len(results) - passed
        return {
            "success": failed == 0,
            "status": "passed" if failed == 0 else "failed",
            "message": f"Run completed: {passed} passed, {failed} failed",
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "results": results,
            "workspace": str(self.root_path),
            "error": None if failed == 0 else "One or more cases failed",
        }

    def _preserve_problem_for_execution(self, record: ExecutionRecord) -> None:
        if record.status not in {"failed", "error"}:
            return

        case_definition = record.metadata.get("case")
        if not isinstance(case_definition, dict):
            return
        case_payload = self._unwrap_case_definition(case_definition)
        if not (
            self._is_api_problem_candidate(case_payload)
            or self._is_data_problem_candidate(case_payload)
            or self._is_service_runtime_problem_candidate(case_payload)
            or self._has_new_crash_dump_refs(record.metadata.get("crash_capture"))
        ):
            return

        environment = record.metadata.get("environment", {})
        objects = record.metadata.get("objects", [])
        artifact_refs = record.metadata.get("artifacts", {})
        if not isinstance(environment, dict) or not isinstance(objects, list):
            return
        if not isinstance(artifact_refs, dict):
            artifact_refs = {}
        environment_id = self._extract_environment_id(environment)
        object_refs = [
            item["name"]
            for item in objects
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        ]
        log_refs = artifact_refs.get("log_index", {})
        if not isinstance(log_refs, dict):
            log_refs = {}
        built = self._build_problem_records(
            record,
            case_payload=case_payload,
            environment_id=environment_id,
            object_refs=object_refs,
            artifact_refs=artifact_refs,
            log_refs=log_refs,
            crash_capture=record.metadata.get("crash_capture"),
        )
        if built is None:
            return
        problem_record, problem_assets = built

        self._save_problem_bundle(problem_record, problem_assets)
        problems = record.metadata.setdefault("problems", [])
        if isinstance(problems, list):
            problem_dict = problem_record.to_dict()
            existing_index = next(
                (
                    idx
                    for idx, item in enumerate(problems)
                    if isinstance(item, dict)
                    and item.get("problem_id") == problem_record.problem_id
                ),
                None,
            )
            if existing_index is None:
                problems.append(problem_dict)
            else:
                problems[existing_index] = problem_dict
            self.storage.save_execution(record)

    def _list_problem_record_models(
        self,
        *,
        case_id: str | None = None,
        execution_id: str | None = None,
    ) -> list[ProblemRecord]:
        if execution_id is not None and case_id is not None:
            execution_records = {
                record.problem_id: record
                for record in self.storage.list_problem_records_for_execution(
                    execution_id
                )
            }
            case_problem_ids = set(self.storage.list_problem_ids_for_case(case_id))
            return [
                record
                for problem_id, record in execution_records.items()
                if problem_id in case_problem_ids
            ]
        if execution_id is not None:
            return self.storage.list_problem_records_for_execution(execution_id)
        if case_id is not None:
            return self.storage.list_problem_records_for_case(case_id)
        return list(self.storage.load_problem_records().values())

    def _existing_object_created_at(self, name: str) -> str:
        record = self.storage.get_object(name)
        if record is None:
            return datetime.now().isoformat()
        return record.created_at

    def _normalize_suite_result(self, item: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(item)
        payload = normalized.get("result")
        if isinstance(payload, TestCaseResult):
            normalized["result"] = self._result_payload(payload)
        return normalized

    def _is_api_problem_candidate(self, case_definition: dict[str, Any]) -> bool:
        case_type = case_definition.get("type")
        return (
            case_type == "api"
            or "request" in case_definition
            or "url" in case_definition
        )

    def _unwrap_case_definition(
        self, case_definition: dict[str, Any]
    ) -> dict[str, Any]:
        payload = case_definition.get("data")
        if isinstance(payload, dict):
            return payload
        return case_definition

    def _extract_api_request(self, case_definition: dict[str, Any]) -> dict[str, Any]:
        request_config = case_definition.get("request", {})
        if not isinstance(request_config, dict):
            request_config = {}
        method = request_config.get("method") or case_definition.get("method", "GET")
        url = request_config.get("url") or case_definition.get("url", "")
        headers = request_config.get("headers") or case_definition.get("headers", {})
        params = request_config.get("params") or case_definition.get("params", {})
        body = request_config.get("body") or case_definition.get("body", {})
        timeout = request_config.get("timeout") or case_definition.get("timeout", 30)
        return {
            "method": method,
            "url": url,
            "headers": headers if isinstance(headers, dict) else {},
            "params": params if isinstance(params, dict) else {},
            "body": body if isinstance(body, dict) else body,
            "timeout": timeout,
        }

    def _extract_environment_id(self, environment: dict[str, Any]) -> str:
        metadata = environment.get("metadata", {})
        if isinstance(metadata, dict):
            isolation = metadata.get("isolation", {})
            if isinstance(isolation, dict):
                env_id = isolation.get("env_id")
                if isinstance(env_id, str):
                    return env_id
        path = environment.get("path", "")
        return path if isinstance(path, str) else ""

    def _build_problem_summary(self, record: ExecutionRecord) -> str:
        error = record.error_message.strip() or "Execution failed"
        return f"API response problem for case '{record.case_id}': {error}"

    def _build_problem_records(
        self,
        record: ExecutionRecord,
        *,
        case_payload: dict[str, Any],
        environment_id: str,
        object_refs: list[str],
        artifact_refs: dict[str, Any],
        log_refs: dict[str, Any],
        crash_capture: Any = None,
    ) -> tuple[ProblemRecord, ProblemAssetRecord] | None:
        if self._is_crash_dump_problem_candidate(
            case_payload
        ) or self._has_new_crash_dump_refs(crash_capture):
            return self._build_crash_dump_problem_records(
                record,
                case_payload=case_payload,
                environment_id=environment_id,
                object_refs=object_refs,
                artifact_refs=artifact_refs,
                log_refs=log_refs,
                crash_capture=crash_capture,
            )
        if self._is_api_problem_candidate(case_payload):
            return self._build_api_problem_records(
                record,
                case_payload=case_payload,
                environment_id=environment_id,
                object_refs=object_refs,
                artifact_refs=artifact_refs,
                log_refs=log_refs,
            )
        if self._is_data_problem_candidate(case_payload):
            return self._build_data_problem_records(
                record,
                case_payload=case_payload,
                environment_id=environment_id,
                object_refs=object_refs,
                artifact_refs=artifact_refs,
                log_refs=log_refs,
            )
        if self._is_service_runtime_problem_candidate(case_payload):
            return self._build_service_runtime_problem_records(
                record,
                case_payload=case_payload,
                environment_id=environment_id,
                object_refs=object_refs,
                artifact_refs=artifact_refs,
                log_refs=log_refs,
            )
        return None

    def _build_api_problem_records(
        self,
        record: ExecutionRecord,
        *,
        case_payload: dict[str, Any],
        environment_id: str,
        object_refs: list[str],
        artifact_refs: dict[str, Any],
        log_refs: dict[str, Any],
    ) -> tuple[ProblemRecord, ProblemAssetRecord]:
        request_payload = self._extract_api_request(case_payload)
        summary = self._build_problem_summary(record)
        problem_id = f"problem_{record.execution_id}"
        now = datetime.now().isoformat()
        problem_artifact_refs = self._problem_artifact_refs(artifact_refs)
        observed_response = self._build_api_observed_response(record, case_payload)
        object_artifacts = self._build_problem_object_artifacts(
            record,
            problem_type="api_response",
            object_refs=object_refs,
        )
        details = {
            "request": request_payload,
            "response": observed_response,
            "case": case_payload,
            "preservation": {},
        }
        if object_artifacts:
            details["object_artifacts"] = object_artifacts
        preservation = self._build_preservation_summary(
            {
                "request_context": (
                    bool(request_payload.get("url")),
                    "request url was not preserved",
                ),
                "response_context": (
                    bool(observed_response["error"] or observed_response["output"]),
                    "response context was not preserved",
                ),
                "environment_ref": (
                    bool(environment_id),
                    "environment reference is not available",
                ),
                "execution_artifacts": (
                    bool(
                        problem_artifact_refs.get("execution_artifacts")
                        or problem_artifact_refs.get("artifact_index")
                    ),
                    "execution artifacts were not preserved",
                ),
                "log_index": (
                    bool(log_refs.get("workspace_logs_dir")),
                    "log index is not available",
                ),
            }
        )
        problem_record = self._new_problem_record(
            problem_id=problem_id,
            problem_type="api_response",
            summary=summary,
            preservation=preservation,
            execution_id=record.execution_id,
            case_id=record.case_id,
            environment_id=environment_id,
            object_refs=object_refs,
            artifact_refs=problem_artifact_refs,
            log_refs=log_refs,
            created_at=now,
            updated_at=now,
            metadata={"source": "execution_failure"},
        )
        problem_assets = self._new_problem_assets(
            problem_id=problem_id,
            problem_type="api_response",
            summary=summary,
            preservation=preservation,
            execution_id=record.execution_id,
            case_id=record.case_id,
            environment_id=environment_id,
            object_refs=object_refs,
            artifact_refs=problem_record.artifact_refs.copy(),
            log_refs=log_refs,
            recovery={
                "replay": request_payload,
                "supported": True,
                "mode": "request_replay",
            },
            details={**details, "preservation": preservation},
            created_at=now,
            updated_at=now,
            metadata={
                "source": "execution_failure",
                "source_execution": record.execution_id,
            },
        )
        return problem_record, problem_assets

    def _build_api_observed_response(
        self, record: ExecutionRecord, case_payload: dict[str, Any]
    ) -> dict[str, Any]:
        assertions = case_payload.get("assertions", [])
        expected_status: int | None = None
        if not assertions:
            raw_expected_status = case_payload.get("expected_status", 200)
            if isinstance(raw_expected_status, int):
                expected_status = raw_expected_status
        expected_response = case_payload.get("expected_response")
        return {
            "output": record.output,
            "error": record.error_message,
            "status": record.status,
            "expected_status": expected_status,
            "expected_response": expected_response,
            "observed_status_code": self._extract_api_observed_status_code(
                record.error_message
            ),
            "observed_body": self._extract_api_observed_body(record),
        }

    def _build_data_problem_records(
        self,
        record: ExecutionRecord,
        *,
        case_payload: dict[str, Any],
        environment_id: str,
        object_refs: list[str],
        artifact_refs: dict[str, Any],
        log_refs: dict[str, Any],
    ) -> tuple[ProblemRecord, ProblemAssetRecord]:
        summary = self._build_data_problem_summary(record)
        problem_id = f"problem_{record.execution_id}"
        now = datetime.now().isoformat()
        database_path = case_payload.get("database", "")
        actual_result = self._extract_data_actual_result(record)
        data_state_analysis = self._analyze_data_state_problem(
            expected_result=case_payload.get("expected_result"),
            actual_result=actual_result,
            query=str(case_payload.get("query", "")),
        )
        origin_hints = self._build_data_state_origin_hints(
            execution_id=record.execution_id,
            case_id=record.case_id,
            failure_kind=data_state_analysis["failure_kind"],
            query=str(case_payload.get("query", "")),
        )
        boundary = self._build_data_state_recovery_boundary(
            failure_kind=data_state_analysis["failure_kind"],
            origin_hints=origin_hints,
        )
        boundary_actions = boundary.get("recommended_actions")
        if not isinstance(boundary_actions, list) or not boundary_actions:
            boundary_actions = data_state_analysis["next_actions"]
        recovery_hints = {
            "supported": False,
            "mode": "minimal_state_hints",
            "db_type": case_payload.get("db_type", "unknown"),
            "database": database_path,
            "query": case_payload.get("query", ""),
            "expected_result": case_payload.get("expected_result"),
            "failure_kind": data_state_analysis["failure_kind"],
            "state_hints": data_state_analysis["state_hints"],
            "origin_hints": origin_hints,
            "boundary": boundary,
            "recommended_queries": data_state_analysis["recommended_queries"],
            "suggested_repairs": data_state_analysis["suggested_repairs"],
            "next_actions": boundary_actions,
            "limitations": data_state_analysis["limitations"],
        }
        details = {
            "data_source": {
                "db_type": case_payload.get("db_type", "unknown"),
                "database": database_path,
                "host": case_payload.get("host"),
                "port": case_payload.get("port"),
            },
            "operations": [
                {
                    "query": case_payload.get("query", ""),
                    "type": "query",
                }
            ],
            "expected_result": case_payload.get("expected_result"),
            "actual_result": actual_result,
            "failure_kind": data_state_analysis["failure_kind"],
            "state_hints": data_state_analysis["state_hints"],
            "origin_hints": origin_hints,
            "error": record.error_message,
            "case": case_payload,
        }
        data_state_artifacts = None
        if isinstance(record.metadata, dict):
            data_state_artifacts = record.metadata.get("data_state_artifacts")
        if isinstance(data_state_artifacts, dict) and data_state_artifacts:
            details["data_state_artifacts"] = data_state_artifacts
            recovery_hints["state_snapshot"] = self._summarize_data_state_artifacts(
                data_state_artifacts
            )
        object_artifacts = self._build_problem_object_artifacts(
            record,
            problem_type="data_state",
            object_refs=object_refs,
        )
        if object_artifacts:
            details["object_artifacts"] = object_artifacts
        preservation = self._build_preservation_summary(
            {
                "data_source": (
                    bool(details["data_source"].get("db_type")),
                    "data source information was not preserved",
                ),
                "operation_trace": (
                    bool(details["operations"][0].get("query")),
                    "query operation trace is not available",
                ),
                "expected_result": (
                    details["expected_result"] is not None,
                    "expected result was not preserved",
                ),
                "actual_result": (
                    actual_result is not None,
                    "actual query result could not be reconstructed",
                ),
                "environment_ref": (
                    bool(environment_id),
                    "environment reference is not available",
                ),
                "execution_artifacts": (
                    bool(
                        artifact_refs.get("directory")
                        or self._problem_artifact_refs(artifact_refs).get(
                            "artifact_index"
                        )
                    ),
                    "execution artifacts were not preserved",
                ),
                "log_index": (
                    bool(log_refs.get("workspace_logs_dir")),
                    "log index is not available",
                ),
                "data_state_snapshot": (
                    isinstance(data_state_artifacts, dict)
                    and data_state_artifacts.get("capture_status") == "available",
                    "data state snapshot is not available",
                ),
            }
        )
        problem_record = self._new_problem_record(
            problem_id=problem_id,
            problem_type="data_state",
            summary=summary,
            preservation=preservation,
            execution_id=record.execution_id,
            case_id=record.case_id,
            environment_id=environment_id,
            object_refs=object_refs,
            artifact_refs=self._problem_artifact_refs(artifact_refs),
            log_refs=log_refs,
            created_at=now,
            updated_at=now,
            metadata={"source": "execution_failure"},
        )
        problem_assets = self._new_problem_assets(
            problem_id=problem_id,
            problem_type="data_state",
            summary=summary,
            preservation=preservation,
            execution_id=record.execution_id,
            case_id=record.case_id,
            environment_id=environment_id,
            object_refs=object_refs,
            artifact_refs=problem_record.artifact_refs.copy(),
            log_refs=log_refs,
            recovery=recovery_hints,
            details={**details, "preservation": preservation},
            created_at=now,
            updated_at=now,
            metadata={
                "source": "execution_failure",
                "source_execution": record.execution_id,
            },
        )
        return problem_record, problem_assets

    def _problem_artifact_refs(self, artifact_refs: dict[str, Any]) -> dict[str, Any]:
        indexes = artifact_refs.get("indexes", {})
        artifact_index = ""
        if isinstance(indexes, dict):
            raw_index = indexes.get("artifact_index", "")
            artifact_index = raw_index if isinstance(raw_index, str) else ""
        return {
            "execution_artifacts": artifact_refs.get("directory", ""),
            "artifact_index": artifact_index,
        }

    def _is_data_problem_candidate(self, case_definition: dict[str, Any]) -> bool:
        case_type = case_definition.get("type")
        return case_type == "database"

    def _is_crash_dump_problem_candidate(self, case_definition: dict[str, Any]) -> bool:
        dump_paths = case_definition.get("dump_paths")
        core_paths = case_definition.get("core_paths")
        return case_definition.get("type") == "service" and (
            isinstance(dump_paths, list)
            and any(isinstance(item, str) and item for item in dump_paths)
            or isinstance(core_paths, list)
            and any(isinstance(item, str) and item for item in core_paths)
        )

    def _build_crash_dump_problem_records(
        self,
        record: ExecutionRecord,
        *,
        case_payload: dict[str, Any],
        environment_id: str,
        object_refs: list[str],
        artifact_refs: dict[str, Any],
        log_refs: dict[str, Any],
        crash_capture: Any = None,
    ) -> tuple[ProblemRecord, ProblemAssetRecord]:
        summary = self._build_crash_dump_problem_summary(record)
        problem_id = f"problem_{record.execution_id}"
        now = datetime.now().isoformat()
        service_name = case_payload.get("service_name", "")
        runtime_object_refs = object_refs.copy()
        if (
            isinstance(service_name, str)
            and service_name
            and service_name not in runtime_object_refs
        ):
            runtime_object_refs.append(service_name)
        object_artifacts = self._build_problem_object_artifacts(
            record,
            problem_type="crash_dump",
            object_refs=runtime_object_refs,
        )

        dump_refs = self._merge_crash_dump_refs(
            self._build_crash_dump_refs(case_payload),
            self._extract_new_crash_dump_refs(crash_capture),
        )
        object_summary = self._build_crash_dump_object_summary(service_name)
        log_window = self._build_crash_dump_log_window(log_refs)
        crash_target = {
            "service_name": service_name,
            "object_name": service_name,
            "runtime_backend": "object_or_external_service",
            "host": case_payload.get("host", "localhost"),
            "port": case_payload.get("port", 8080),
        }
        boundary = self._build_crash_dump_boundary(dump_refs)
        recovery = {
            "supported": False,
            "mode": "crash_dump_investigation",
            "crash_target": crash_target,
            "dump_refs": dump_refs,
            "object_summary": object_summary,
            "log_window": log_window,
            "boundary": boundary,
            "recommended_checks": self._build_crash_dump_recommended_checks(
                dump_refs=dump_refs,
                crash_target=crash_target,
            ),
            "next_actions": self._build_crash_dump_next_actions(dump_refs),
            "limitations": [
                "current crash_dump recovery preserves dump/core references but does not parse dump contents",
                "current crash_dump recovery does not reconstruct historical runtime state automatically",
            ],
        }
        details = {
            "crash_target": crash_target,
            "crash_event": {
                "detected_at": record.end_time or now,
                "execution_status": record.status,
                "error": record.error_message,
                "output": record.output,
            },
            "runtime_context": {
                "expected_runtime_state": case_payload.get("expected_runtime_state"),
                "check_type": case_payload.get("check_type", "port"),
            },
            "dump_refs": dump_refs,
            "object_summary": object_summary,
            "log_window": log_window,
            "crash_capture": crash_capture if isinstance(crash_capture, dict) else {},
            "case": case_payload,
        }
        if object_artifacts:
            details["object_artifacts"] = object_artifacts
        preservation = self._build_preservation_summary(
            {
                "crash_target": (
                    bool(service_name),
                    "crash target identity was not preserved",
                ),
                "dump_refs": (
                    bool(dump_refs),
                    "no dump/core references were preserved",
                ),
                "runtime_result": (
                    bool(record.error_message or record.output),
                    "runtime failure context was not preserved",
                ),
                "environment_ref": (
                    bool(environment_id),
                    "environment reference is not available",
                ),
                "execution_artifacts": (
                    bool(
                        artifact_refs.get("directory")
                        or self._problem_artifact_refs(artifact_refs).get(
                            "artifact_index"
                        )
                    ),
                    "execution artifacts were not preserved",
                ),
                "log_index": (
                    bool(log_refs.get("workspace_logs_dir")),
                    "log index is not available",
                ),
            }
        )
        problem_record = self._new_problem_record(
            problem_id=problem_id,
            problem_type="crash_dump",
            summary=summary,
            preservation=preservation,
            execution_id=record.execution_id,
            case_id=record.case_id,
            environment_id=environment_id,
            object_refs=runtime_object_refs,
            artifact_refs=self._problem_artifact_refs(artifact_refs),
            log_refs=log_refs,
            created_at=now,
            updated_at=now,
            metadata={"source": "execution_failure"},
        )
        problem_assets = self._new_problem_assets(
            problem_id=problem_id,
            problem_type="crash_dump",
            summary=summary,
            preservation=preservation,
            execution_id=record.execution_id,
            case_id=record.case_id,
            environment_id=environment_id,
            object_refs=runtime_object_refs,
            artifact_refs=problem_record.artifact_refs.copy(),
            log_refs=log_refs,
            recovery=recovery,
            details={**details, "preservation": preservation},
            created_at=now,
            updated_at=now,
            metadata={
                "source": "execution_failure",
                "source_execution": record.execution_id,
            },
        )
        return problem_record, problem_assets

    def _build_crash_dump_problem_summary(self, record: ExecutionRecord) -> str:
        error = record.error_message.strip() or "Crash or dump-producing failure"
        return f"Crash/dump problem for case '{record.case_id}': {error}"

    def _build_crash_dump_refs(
        self, case_payload: dict[str, Any]
    ) -> list[dict[str, Any]]:
        raw_paths = case_payload.get("dump_paths", case_payload.get("core_paths", []))
        if not isinstance(raw_paths, list):
            return []
        refs: list[dict[str, Any]] = []
        for item in raw_paths:
            if not isinstance(item, str) or not item:
                continue
            path = Path(item).expanduser()
            exists = path.exists()
            stat = path.stat() if exists else None
            refs.append(
                {
                    "path": str(path),
                    "exists": exists,
                    "kind": "core_or_dump",
                    "name": path.name,
                    "size": stat.st_size if stat is not None else None,
                    "modified_at": (
                        datetime.fromtimestamp(stat.st_mtime).isoformat()
                        if stat is not None
                        else None
                    ),
                }
            )
        return refs

    def _capture_workspace_crash_dump_snapshot(
        self,
        case_definition: dict[str, Any] | None,
    ) -> dict[str, Any]:
        case_payload = (
            self._unwrap_case_definition(case_definition)
            if isinstance(case_definition, dict)
            else {}
        )
        directories = self._resolve_crash_dump_watch_directories(case_payload)
        refs: list[dict[str, Any]] = []
        for directory in directories:
            refs.extend(self._scan_crash_dump_directory(directory))
        return {
            "captured_at": datetime.now().isoformat(),
            "directories": directories,
            "dump_refs": refs,
        }

    def _resolve_crash_dump_watch_directories(
        self,
        case_payload: dict[str, Any],
    ) -> list[str]:
        directories: list[str] = []
        environment = self.storage.load_environment()
        if environment and isinstance(environment.metadata, dict):
            env_crash_capture = environment.metadata.get("crash_capture", {})
            if isinstance(env_crash_capture, dict):
                dump_dir = env_crash_capture.get("dump_dir")
                if isinstance(dump_dir, str) and dump_dir:
                    directories.append(str(Path(dump_dir).expanduser().resolve()))

        target_name = case_payload.get("object_name") or case_payload.get(
            "service_name"
        )
        if isinstance(target_name, str) and target_name:
            record = self.storage.get_object(target_name)
            if record is not None and isinstance(record.metadata, dict):
                object_crash_capture = record.metadata.get("crash_capture", {})
                if isinstance(object_crash_capture, dict):
                    dump_dir = object_crash_capture.get("dump_dir")
                    if isinstance(dump_dir, str) and dump_dir:
                        directories.append(str(Path(dump_dir).expanduser().resolve()))

        unique: list[str] = []
        seen: set[str] = set()
        for directory in directories:
            if directory in seen:
                continue
            seen.add(directory)
            unique.append(directory)
        return unique

    def _scan_crash_dump_directory(self, directory: str) -> list[dict[str, Any]]:
        path = Path(directory)
        if not path.exists() or not path.is_dir():
            return []
        refs: list[dict[str, Any]] = []
        for item in sorted(path.rglob("*")):
            if not item.is_file() or not self._looks_like_crash_dump_file(item):
                continue
            stat = item.stat()
            refs.append(
                {
                    "path": str(item.resolve()),
                    "exists": True,
                    "kind": "core_or_dump",
                    "name": item.name,
                    "size": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "source": "workspace_scan",
                    "directory": str(path.resolve()),
                }
            )
        return refs

    def _looks_like_crash_dump_file(self, path: Path) -> bool:
        name = path.name.lower()
        return (
            name.startswith("core")
            or name.endswith(".core")
            or name.endswith(".dump")
            or name.endswith(".dmp")
        )

    def _detect_new_crash_dump_refs(
        self,
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> list[dict[str, Any]]:
        before_refs = before.get("dump_refs", []) if isinstance(before, dict) else []
        after_refs = after.get("dump_refs", []) if isinstance(after, dict) else []
        if not isinstance(before_refs, list) or not isinstance(after_refs, list):
            return []
        before_paths = {
            str(item.get("path"))
            for item in before_refs
            if isinstance(item, dict) and isinstance(item.get("path"), str)
        }
        return [
            item
            for item in after_refs
            if isinstance(item, dict)
            and isinstance(item.get("path"), str)
            and item["path"] not in before_paths
        ]

    def _has_new_crash_dump_refs(self, crash_capture: Any) -> bool:
        if not isinstance(crash_capture, dict):
            return False
        refs = crash_capture.get("new_dump_refs", [])
        return isinstance(refs, list) and bool(refs)

    def _extract_new_crash_dump_refs(self, crash_capture: Any) -> list[dict[str, Any]]:
        if not isinstance(crash_capture, dict):
            return []
        refs = crash_capture.get("new_dump_refs", [])
        if not isinstance(refs, list):
            return []
        return [item for item in refs if isinstance(item, dict)]

    def _merge_crash_dump_refs(
        self,
        explicit_refs: list[dict[str, Any]],
        auto_refs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen: set[str] = set()
        for ref in [*explicit_refs, *auto_refs]:
            path = ref.get("path")
            if not isinstance(path, str) or path in seen:
                continue
            seen.add(path)
            merged.append(ref)
        return merged

    def _build_crash_dump_boundary(
        self, dump_refs: list[dict[str, Any]]
    ) -> dict[str, Any]:
        existing_refs = [ref for ref in dump_refs if ref.get("exists") is True]
        return {
            "scope": "crash_asset_preservation",
            "confidence": (
                "high_for_existing_dump_refs"
                if existing_refs
                else "reference_only_without_dump_file"
            ),
            "assessment": (
                "dump_refs_preserved_for_followup_analysis"
                if existing_refs
                else "dump_refs_declared_but_dump_not_found"
            ),
            "reason": (
                "the current crash_dump flow preserves dump/core references for follow-up investigation but does not parse dump contents"
            ),
            "needs_dump_analysis": True,
        }

    def _build_crash_dump_recommended_checks(
        self,
        *,
        dump_refs: list[dict[str, Any]],
        crash_target: dict[str, Any],
    ) -> list[dict[str, Any]]:
        return [
            {
                "purpose": "inspect_dump_refs",
                "dump_count": len(dump_refs),
            },
            {
                "purpose": "inspect_recent_runtime_logs",
                "service_name": crash_target.get("service_name"),
            },
            {
                "purpose": "inspect_runtime_target",
                "host": crash_target.get("host"),
                "port": crash_target.get("port"),
            },
        ]

    def _build_crash_dump_next_actions(
        self, dump_refs: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        actions = [
            {
                "priority": "high",
                "action": "inspect_dump_refs",
                "reason": "verify whether the preserved dump/core files are present and complete",
            },
            {
                "priority": "high",
                "action": "inspect_recent_runtime_logs",
                "reason": "use the crash window logs to confirm pre-crash runtime context",
            },
        ]
        if any(ref.get("exists") is True for ref in dump_refs):
            actions.append(
                {
                    "priority": "medium",
                    "action": "prepare_followup_dump_analysis",
                    "reason": "the dump/core asset exists and can be used in a deeper crash investigation phase",
                }
            )
        return actions

    def _build_data_problem_summary(self, record: ExecutionRecord) -> str:
        error = record.error_message.strip() or "Execution failed"
        return f"Data/state problem for case '{record.case_id}': {error}"

    def _is_service_runtime_problem_candidate(
        self, case_definition: dict[str, Any]
    ) -> bool:
        return case_definition.get("type") == "service"

    def _build_service_runtime_problem_records(
        self,
        record: ExecutionRecord,
        *,
        case_payload: dict[str, Any],
        environment_id: str,
        object_refs: list[str],
        artifact_refs: dict[str, Any],
        log_refs: dict[str, Any],
    ) -> tuple[ProblemRecord, ProblemAssetRecord]:
        summary = self._build_service_runtime_problem_summary(record)
        problem_id = f"problem_{record.execution_id}"
        now = datetime.now().isoformat()
        service_name = case_payload.get("service_name", "")
        runtime_object_refs = object_refs.copy()
        if (
            isinstance(service_name, str)
            and service_name
            and service_name not in runtime_object_refs
        ):
            runtime_object_refs.append(service_name)
        object_artifacts = self._build_problem_object_artifacts(
            record,
            problem_type="service_runtime",
            object_refs=runtime_object_refs,
        )

        details = {
            "service": {
                "service_name": service_name,
                "host": case_payload.get("host", "localhost"),
                "port": case_payload.get("port", 8080),
                "check_type": case_payload.get("check_type", "port"),
                "timeout": case_payload.get("timeout", 10),
            },
            "runtime_result": {
                "status": record.status,
                "error": record.error_message,
                "output": record.output,
            },
            "case": case_payload,
        }
        if object_artifacts:
            details["object_artifacts"] = object_artifacts
        runtime_hints = self._build_service_runtime_hints(
            case_payload=case_payload,
            record=record,
            service_name=service_name,
        )
        boundary = self._build_service_runtime_recovery_boundary(runtime_hints)
        recovery = {
            "supported": False,
            "mode": "runtime_level_plan",
            "service_name": service_name,
            "host": case_payload.get("host", "localhost"),
            "port": case_payload.get("port", 8080),
            "check_type": case_payload.get("check_type", "port"),
            "runtime_target": {
                "service_name": service_name,
                "object_name": service_name,
                "runtime_backend": "object_or_external_service",
                "host": case_payload.get("host", "localhost"),
                "port": case_payload.get("port", 8080),
            },
            "failure_kind": runtime_hints["failure_kind"],
            "runtime_hints": runtime_hints,
            "recommended_checks": self._build_service_runtime_recommended_checks(
                case_payload=case_payload,
                runtime_hints=runtime_hints,
            ),
            "suggested_repairs": self._build_service_runtime_suggested_repairs(
                case_payload=case_payload,
                runtime_hints=runtime_hints,
            ),
            "next_actions": self._build_service_runtime_next_actions(
                case_payload=case_payload,
                runtime_hints=runtime_hints,
            ),
            "limitations": [
                "current recovery output is a plan only and does not execute service recovery automatically",
                "current service_runtime recovery does not reconstruct full historical runtime context",
            ],
            "boundary": boundary,
        }
        details["failure_kind"] = runtime_hints["failure_kind"]
        details["runtime_hints"] = runtime_hints
        preservation = self._build_preservation_summary(
            {
                "service_context": (
                    bool(service_name),
                    "service identity was not preserved",
                ),
                "runtime_result": (
                    bool(record.error_message or record.output),
                    "runtime result was not preserved",
                ),
                "environment_ref": (
                    bool(environment_id),
                    "environment reference is not available",
                ),
                "execution_artifacts": (
                    bool(
                        artifact_refs.get("directory")
                        or self._problem_artifact_refs(artifact_refs).get(
                            "artifact_index"
                        )
                    ),
                    "execution artifacts were not preserved",
                ),
                "log_index": (
                    bool(log_refs.get("workspace_logs_dir")),
                    "log index is not available",
                ),
            }
        )
        problem_record = self._new_problem_record(
            problem_id=problem_id,
            problem_type="service_runtime",
            summary=summary,
            preservation=preservation,
            execution_id=record.execution_id,
            case_id=record.case_id,
            environment_id=environment_id,
            object_refs=runtime_object_refs,
            artifact_refs=self._problem_artifact_refs(artifact_refs),
            log_refs=log_refs,
            created_at=now,
            updated_at=now,
            metadata={"source": "execution_failure"},
        )
        problem_assets = self._new_problem_assets(
            problem_id=problem_id,
            problem_type="service_runtime",
            summary=summary,
            preservation=preservation,
            execution_id=record.execution_id,
            case_id=record.case_id,
            environment_id=environment_id,
            object_refs=runtime_object_refs,
            artifact_refs=problem_record.artifact_refs.copy(),
            log_refs=log_refs,
            recovery=recovery,
            details={**details, "preservation": preservation},
            created_at=now,
            updated_at=now,
            metadata={
                "source": "execution_failure",
                "source_execution": record.execution_id,
            },
        )
        return problem_record, problem_assets

    def _build_service_runtime_problem_summary(self, record: ExecutionRecord) -> str:
        error = record.error_message.strip() or "Execution failed"
        return f"Service runtime problem for case '{record.case_id}': {error}"

    def _build_service_runtime_hints(
        self,
        *,
        case_payload: dict[str, Any],
        record: ExecutionRecord,
        service_name: str,
    ) -> dict[str, Any]:
        host = case_payload.get("host", "localhost")
        port = case_payload.get("port", 8080)
        check_type = str(case_payload.get("check_type", "port"))
        object_record = (
            self.storage.get_object(service_name)
            if isinstance(service_name, str) and service_name
            else None
        )
        object_status = object_record.status if object_record is not None else None
        expected_runtime_state = str(
            case_payload.get("expected_runtime_state", "")
        ).lower()
        error_text = str(record.error_message or "")
        error_lower = error_text.lower()

        failure_kind = "healthcheck_failed"
        if object_status == OBJECT_STATUS_START_FAILED_PRESERVED:
            failure_kind = "startup_failed"
        elif object_status in {
            OBJECT_STATUS_CREATED,
            OBJECT_STATUS_INSTALLED,
            OBJECT_STATUS_STOPPED,
            OBJECT_STATUS_REMOVED,
        }:
            failure_kind = "not_started"
        elif object_status == OBJECT_STATUS_ERROR:
            failure_kind = "abnormal_exit"
        elif "not reachable" in error_lower:
            if (
                object_status == OBJECT_STATUS_RUNNING
                or expected_runtime_state == "running"
            ):
                failure_kind = "abnormal_exit"
            else:
                failure_kind = "port_unreachable"
        elif "unsupported check type" in error_lower:
            failure_kind = "healthcheck_failed"
        elif "timeout" in error_lower or "timed out" in error_lower:
            failure_kind = "healthcheck_failed"
        elif "connection refused" in error_lower or "connection reset" in error_lower:
            failure_kind = "port_unreachable"

        return {
            "object_status": object_status,
            "check_type": check_type,
            "connectable": False,
            "host": host,
            "port": port,
            "expected_runtime_state": expected_runtime_state or None,
            "error_keywords": self._extract_service_runtime_error_keywords(error_text),
            "failure_kind": failure_kind,
        }

    def _extract_service_runtime_error_keywords(self, error_text: str) -> list[str]:
        keywords: list[str] = []
        lowered = error_text.lower()
        if "not reachable" in lowered:
            keywords.append("not_reachable")
        if "timeout" in lowered or "timed out" in lowered:
            keywords.append("timeout")
        if "connection refused" in lowered:
            keywords.append("connection_refused")
        if "unsupported check type" in lowered:
            keywords.append("unsupported_check_type")
        if "error" in lowered and "service test error" in lowered:
            keywords.append("service_test_error")
        return keywords

    def _build_service_runtime_recovery_boundary(
        self, runtime_hints: dict[str, Any]
    ) -> dict[str, Any]:
        failure_kind = str(runtime_hints.get("failure_kind", "healthcheck_failed"))
        object_status = runtime_hints.get("object_status")
        expected_runtime_state = str(
            runtime_hints.get("expected_runtime_state") or ""
        ).lower()
        confidence = "runtime_observation_only"
        assessment = "endpoint_or_healthcheck_failure"
        reason = "current recovery plan is based on preserved runtime observations and does not reconstruct full service history"
        if failure_kind == "startup_failed":
            confidence = "high_for_preserved_start_failure"
            assessment = "startup_failure_detected"
            reason = "the related managed object is preserved in a start-failed state"
        elif failure_kind == "not_started":
            confidence = "high_for_non_running_object"
            assessment = "service_not_started"
            reason = "the related managed object is not currently in a running state"
        elif failure_kind == "abnormal_exit":
            if (
                object_status == OBJECT_STATUS_RUNNING
                or expected_runtime_state == "running"
            ):
                confidence = "high_for_expected_running_service"
            else:
                confidence = "reduced_by_runtime_state_gap"
            assessment = "runtime_diverged_from_expected_service_state"
            reason = "the service was expected to be running but current runtime observations suggest it exited or became unreachable"
        return {
            "scope": "runtime_level_plan",
            "confidence": confidence,
            "assessment": assessment,
            "reason": reason,
            "needs_runtime_history": failure_kind in {"abnormal_exit"},
            "does_not_cover": [
                "automatic_service_restart",
                "core_dump_analysis",
                "deep_resource_diagnostics",
            ],
        }

    def _build_service_runtime_recommended_checks(
        self, *, case_payload: dict[str, Any], runtime_hints: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return [
            {
                "purpose": "inspect_runtime_status",
                "check_type": runtime_hints.get("check_type"),
                "host": case_payload.get("host", "localhost"),
                "port": case_payload.get("port", 8080),
            },
            {
                "purpose": "inspect_recent_runtime_logs",
                "service_name": case_payload.get("service_name", ""),
            },
        ]

    def _build_service_runtime_suggested_repairs(
        self, *, case_payload: dict[str, Any], runtime_hints: dict[str, Any]
    ) -> list[dict[str, Any]]:
        failure_kind = str(runtime_hints.get("failure_kind", "healthcheck_failed"))
        service_name = case_payload.get("service_name", "")
        if failure_kind == "startup_failed":
            return [
                {
                    "action": "inspect_start_failure_and_fix_prerequisites",
                    "service_name": service_name,
                    "reason": "the service failed during startup and should be checked before any retry",
                }
            ]
        if failure_kind == "not_started":
            return [
                {
                    "action": "start_service_or_verify_runtime_preconditions",
                    "service_name": service_name,
                    "reason": "the service is not currently running",
                }
            ]
        if failure_kind == "abnormal_exit":
            return [
                {
                    "action": "inspect_exit_logs_before_restart",
                    "service_name": service_name,
                    "reason": "the service appears to have exited after being expected to run",
                }
            ]
        if failure_kind == "port_unreachable":
            return [
                {
                    "action": "verify_endpoint_reachability_and_port_binding",
                    "service_name": service_name,
                    "reason": "the preserved runtime check could not reach the configured endpoint",
                }
            ]
        return [
            {
                "action": "inspect_healthcheck_configuration",
                "service_name": service_name,
                "reason": "the runtime validation failed and needs a focused healthcheck review",
            }
        ]

    def _build_service_runtime_next_actions(
        self, *, case_payload: dict[str, Any], runtime_hints: dict[str, Any]
    ) -> list[dict[str, Any]]:
        actions = [
            {
                "priority": "high",
                "action": "inspect_recent_runtime_logs",
                "service_name": case_payload.get("service_name", ""),
                "reason": "check the latest runtime failure context before retrying the preserved validation",
            }
        ]
        failure_kind = str(runtime_hints.get("failure_kind", "healthcheck_failed"))
        if failure_kind in {"not_started", "startup_failed"}:
            actions.append(
                {
                    "priority": "high",
                    "action": "retry_service_start_after_prerequisite_check",
                    "service_name": case_payload.get("service_name", ""),
                    "reason": "confirm the service can enter a healthy running state before rerunning the check",
                }
            )
        else:
            actions.append(
                {
                    "priority": "high",
                    "action": "rerun_runtime_validation",
                    "service_name": case_payload.get("service_name", ""),
                    "reason": "rerun the preserved runtime check after validating endpoint availability",
                }
            )
        return actions

    def _extract_data_actual_result(self, record: ExecutionRecord) -> Any:
        if record.output not in (None, ""):
            return record.output
        marker = "Actual:"
        if marker not in record.error_message:
            return None
        raw_actual = record.error_message.split(marker, maxsplit=1)[1].strip()
        try:
            return ast.literal_eval(raw_actual)
        except (SyntaxError, ValueError):
            return raw_actual

    def _extract_api_observed_status_code(self, error_message: str) -> int | None:
        matched = re.search(r"Expected status \d+, got (\d+)", error_message)
        if matched is None:
            return None
        try:
            return int(matched.group(1))
        except ValueError:
            return None

    def _extract_api_observed_body(self, record: ExecutionRecord) -> Any:
        if record.output not in (None, ""):
            return record.output
        marker = "Actual:"
        if marker not in record.error_message:
            return None
        raw_actual = record.error_message.split(marker, maxsplit=1)[1].strip()
        try:
            return ast.literal_eval(raw_actual)
        except (SyntaxError, ValueError):
            return raw_actual

    def _compare_problem_values(self, expected: Any, actual: Any) -> bool:
        if isinstance(expected, dict) and isinstance(actual, dict):
            for key, expected_value in expected.items():
                if key not in actual:
                    return False
                if not self._compare_problem_values(expected_value, actual[key]):
                    return False
            return True
        if isinstance(expected, list) and isinstance(actual, list):
            if len(expected) != len(actual):
                return False
            for exp_item, act_item in zip(expected, actual):
                if not self._compare_problem_values(exp_item, act_item):
                    return False
            return True
        return expected == actual

    def _evaluate_api_assertions(
        self,
        response: _ReplayResponseView,
        assertions_config: list[Any],
    ) -> list[str]:
        failures: list[str] = []
        actual_json = None
        content_type = str(response.headers.get("content-type", ""))
        if content_type.startswith("application/json"):
            try:
                actual_json = response.json()
            except Exception:
                actual_json = None

        for idx, assertion_item in enumerate(assertions_config):
            if not isinstance(assertion_item, dict):
                failures.append(f"Assertion {idx}: invalid format")
                continue
            assertion_type = assertion_item.get("type", "")
            if not assertion_type:
                failures.append(f"Assertion {idx}: missing 'type'")
                continue

            try:
                actual: Any
                expected: Any
                kwargs: dict[str, Any]
                if assertion_type in ("status_code", "statuscode"):
                    actual = response.status_code
                    expected = assertion_item.get("expected")
                    kwargs = {}
                elif assertion_type in ("json_path", "jsonpath"):
                    actual = actual_json if actual_json is not None else {}
                    expected = assertion_item.get("expected")
                    kwargs = {"path": assertion_item.get("path", "")}
                elif assertion_type in ("body", "bodyassertion"):
                    actual = response.text
                    expected = assertion_item.get("expected")
                    kwargs = {}
                elif assertion_type in ("header", "headerassertion"):
                    actual = dict(response.headers)
                    expected = assertion_item.get("expected")
                    kwargs = {"header_name": assertion_item.get("header", "")}
                elif assertion_type in ("regex", "regexassertion"):
                    actual = response.text
                    expected = assertion_item.get("expected")
                    kwargs = {}
                elif assertion_type in ("schema", "schemaassertion"):
                    actual = actual_json if actual_json is not None else {}
                    expected = assertion_item.get("expected")
                    kwargs = {"schema": assertion_item.get("schema", {})}
                else:
                    actual = response
                    expected = assertion_item.get("expected")
                    kwargs = {
                        key: value
                        for key, value in assertion_item.items()
                        if key not in ("type", "expected", "description")
                    }
                assertion = AssertionFactory.create(assertion_type)
                result = assertion.assert_value(actual, expected=expected, **kwargs)
                if result.passed:
                    continue
                message = f"Assertion {idx} ({assertion_type}) failed: {result.message}"
                if result.extra:
                    message += f" - {result.extra}"
                failures.append(message)
            except ValueError as exc:
                failures.append(f"Assertion {idx} ({assertion_type}): {str(exc)}")
            except Exception as exc:
                failures.append(
                    f"Assertion {idx} ({assertion_type}): unexpected error: {str(exc)}"
                )

        return failures

    def _evaluate_api_replay_expectation(
        self,
        case_payload: dict[str, Any],
        replay_response: dict[str, Any],
    ) -> dict[str, Any]:
        status_code = int(replay_response.get("status_code", 0))
        headers = replay_response.get("headers", {})
        body = replay_response.get("body")
        response_view = _ReplayResponseView(
            status_code=status_code,
            headers=headers if isinstance(headers, dict) else {},
            body=body,
        )
        assertions = case_payload.get("assertions", [])
        if assertions:
            failures = self._evaluate_api_assertions(response_view, assertions)
            reproduced = bool(failures)
            return {
                "reproduced": reproduced,
                "status": "reproduced" if reproduced else "not_reproduced",
                "reason": (
                    failures[0]
                    if failures
                    else "replay response now satisfies the original assertions"
                ),
                "failed_assertions": failures,
            }

        expected_status = case_payload.get("expected_status", 200)
        if isinstance(expected_status, int) and status_code != expected_status:
            return {
                "reproduced": True,
                "status": "reproduced",
                "reason": f"Expected status {expected_status}, got {status_code}",
                "expected_status": expected_status,
                "actual_status": status_code,
                "failed_assertions": [],
            }

        expected_response = case_payload.get("expected_response", {})
        if expected_response:
            if not self._compare_problem_values(expected_response, body):
                return {
                    "reproduced": True,
                    "status": "reproduced",
                    "reason": "Replay response body still does not match expected_response",
                    "expected_response": expected_response,
                    "actual_response": body,
                    "failed_assertions": [],
                }

        return {
            "reproduced": False,
            "status": "not_reproduced",
            "reason": "replay response now satisfies the original expectation",
            "expected_status": expected_status
            if isinstance(expected_status, int)
            else None,
            "failed_assertions": [],
        }

    def _build_api_replay_comparison(
        self,
        assets: ProblemAssetRecord,
        replay_result: dict[str, Any],
    ) -> dict[str, Any]:
        details = assets.details if isinstance(assets.details, dict) else {}
        case_payload = details.get("case", {})
        preserved_response = details.get("response", {})
        replay_response = replay_result.get("response", {})
        expectation = self._evaluate_api_replay_expectation(
            case_payload if isinstance(case_payload, dict) else {},
            replay_response if isinstance(replay_response, dict) else {},
        )

        preserved_status = (
            preserved_response.get("observed_status_code")
            if isinstance(preserved_response, dict)
            else None
        )
        replay_status = (
            replay_response.get("status_code")
            if isinstance(replay_response, dict)
            else None
        )
        preserved_body = (
            preserved_response.get("observed_body")
            if isinstance(preserved_response, dict)
            else None
        )
        replay_body = (
            replay_response.get("body") if isinstance(replay_response, dict) else None
        )
        status_code_changed = (
            None
            if preserved_status is None or replay_status is None
            else preserved_status != replay_status
        )
        response_body_changed = (
            None
            if preserved_body is None
            else not self._compare_problem_values(preserved_body, replay_body)
        )
        dependency_hints = self._build_problem_dependency_hints(
            execution_id=assets.execution_id,
            case_id=assets.case_id,
        )
        boundary = self._build_api_replay_boundary_summary(
            expectation=expectation,
            status_code_changed=status_code_changed,
            response_body_changed=response_body_changed,
            dependency_hints=dependency_hints,
        )
        highlights = self._build_api_replay_highlights(
            preserved_status=preserved_status,
            replay_status=replay_status,
            status_code_changed=status_code_changed,
            response_body_changed=response_body_changed,
            expectation=expectation,
            boundary=boundary,
        )
        summary = self._build_api_replay_summary(
            preserved_response=(
                preserved_response if isinstance(preserved_response, dict) else {}
            ),
            replay_response=replay_response
            if isinstance(replay_response, dict)
            else {},
            expectation=expectation,
            status_code_changed=status_code_changed,
            response_body_changed=response_body_changed,
            boundary=boundary,
        )
        return {
            "original_failure": {
                "status_code": preserved_status,
                "body": preserved_body,
                "error": (
                    preserved_response.get("error")
                    if isinstance(preserved_response, dict)
                    else None
                ),
            },
            "replay_response": {
                "status_code": replay_status,
                "body": replay_body,
            },
            "status_code_changed": status_code_changed,
            "response_body_changed": response_body_changed,
            "expectation": expectation,
            "assertion_outcome": expectation["status"],
            "boundary": boundary,
            "highlights": highlights,
            "summary": summary,
        }

    def _build_api_replay_highlights(
        self,
        *,
        preserved_status: Any,
        replay_status: Any,
        status_code_changed: bool | None,
        response_body_changed: bool | None,
        expectation: dict[str, Any],
        boundary: dict[str, Any],
    ) -> list[str]:
        highlights: list[str] = []
        if status_code_changed is True:
            highlights.append(
                f"status code changed from {preserved_status} to {replay_status}"
            )
        elif status_code_changed is False and replay_status is not None:
            highlights.append(f"status code stayed at {replay_status}")

        if response_body_changed is True:
            highlights.append(
                "response body changed compared with the preserved failure"
            )
        elif response_body_changed is False:
            highlights.append("response body stayed the same as the preserved failure")

        if expectation.get("reproduced") is True:
            highlights.append("replay still reproduces the original problem")
        else:
            highlights.append("replay no longer reproduces the original problem")

        reason = expectation.get("reason")
        if isinstance(reason, str) and reason:
            highlights.append(reason)

        boundary_reason = boundary.get("reason")
        if isinstance(boundary_reason, str) and boundary_reason:
            highlights.append(boundary_reason)

        recommended_actions = boundary.get("recommended_actions")
        if isinstance(recommended_actions, list) and recommended_actions:
            first_action = recommended_actions[0]
            if isinstance(first_action, dict):
                action_name = first_action.get("action")
                if isinstance(action_name, str) and action_name:
                    highlights.append(f"next suggested step: {action_name}")

        return highlights

    def _build_api_replay_summary(
        self,
        *,
        preserved_response: dict[str, Any],
        replay_response: dict[str, Any],
        expectation: dict[str, Any],
        status_code_changed: bool | None,
        response_body_changed: bool | None,
        boundary: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "reproduced": expectation.get("reproduced"),
            "assertion_outcome": expectation.get("status"),
            "status": {
                "changed": status_code_changed,
                "from": preserved_response.get("observed_status_code"),
                "to": replay_response.get("status_code"),
            },
            "boundary": boundary,
            "headers": self._build_api_replay_header_summary(replay_response),
            "body": self._build_api_replay_body_summary(
                preserved_body=preserved_response.get("observed_body"),
                replay_body=replay_response.get("body"),
                response_body_changed=response_body_changed,
            ),
        }

    def _build_api_replay_boundary_summary(
        self,
        *,
        expectation: dict[str, Any],
        status_code_changed: bool | None,
        response_body_changed: bool | None,
        dependency_hints: dict[str, Any],
    ) -> dict[str, Any]:
        reproduced = expectation.get("reproduced") is True
        has_dependency_candidates = bool(dependency_hints.get("candidate_case_ids"))
        dependency_case_ids = dependency_hints.get("candidate_case_ids", [])
        recommended_actions = dependency_hints.get("recommended_actions", [])
        dependency_suffix = ""
        if isinstance(dependency_case_ids, list) and dependency_case_ids:
            dependency_suffix = (
                f"; recent preceding cases: {', '.join(map(str, dependency_case_ids))}"
            )
        hidden_dependency_possible = reproduced is False and (
            status_code_changed is True
            or response_body_changed is True
            or has_dependency_candidates
        )

        if reproduced:
            confidence = "request_reproduced"
            assessment = "reproduced_under_current_workspace_state"
            reason = (
                "current replay reproduces the preserved request-level failure "
                "under the current workspace state"
            )
        elif hidden_dependency_possible:
            confidence = "request_only"
            assessment = "diverged_from_preserved_failure"
            reason = (
                "current replay only reruns the preserved request and may miss "
                "prior state changes or hidden dependencies"
                f"{dependency_suffix}"
            )
        else:
            confidence = "request_only"
            assessment = "not_reproduced_under_current_workspace_state"
            reason = (
                "current replay reruns only the preserved request and does not "
                "recreate historical environment state"
                f"{dependency_suffix}"
            )

        return {
            "scope": "request_level",
            "confidence": confidence,
            "assessment": assessment,
            "recreates_environment_state": False,
            "replays_prior_case_effects": False,
            "hidden_dependency_possible": hidden_dependency_possible,
            "dependency_hints": dependency_hints,
            "recommended_actions": recommended_actions,
            "reason": reason,
        }

    def _build_problem_dependency_hints(
        self,
        *,
        execution_id: str,
        case_id: str,
        limit: int = 3,
    ) -> dict[str, Any]:
        if not execution_id:
            return {
                "recent_predecessors": [],
                "candidate_case_ids": [],
                "recent_same_case": None,
                "immediate_predecessor": None,
                "signal_strength": "none",
                "recommended_actions": [],
            }

        records = sorted(
            self.storage.list_executions(),
            key=lambda item: (item.end_time, item.start_time, item.execution_id),
        )
        current_index = next(
            (
                index
                for index, item in enumerate(records)
                if item.execution_id == execution_id
            ),
            None,
        )
        if current_index is None:
            return {
                "recent_predecessors": [],
                "candidate_case_ids": [],
                "recent_same_case": None,
                "immediate_predecessor": None,
                "signal_strength": "none",
                "recommended_actions": [],
            }

        predecessors = records[:current_index]
        recent_predecessors = predecessors[-limit:]
        predecessor_payloads = [
            {
                "execution_id": item.execution_id,
                "case_id": item.case_id,
                "status": item.status,
                "end_time": item.end_time,
            }
            for item in reversed(recent_predecessors)
        ]
        immediate_predecessor = (
            predecessor_payloads[0] if predecessor_payloads else None
        )
        recent_same_case = next(
            (
                {
                    "execution_id": item.execution_id,
                    "case_id": item.case_id,
                    "status": item.status,
                    "end_time": item.end_time,
                }
                for item in reversed(predecessors)
                if item.case_id == case_id
            ),
            None,
        )
        candidate_case_ids: list[str] = []
        for item in predecessor_payloads:
            predecessor_case_id = item["case_id"]
            if predecessor_case_id == case_id:
                continue
            if predecessor_case_id not in candidate_case_ids:
                candidate_case_ids.append(predecessor_case_id)

        signal_strength = self._classify_problem_dependency_signal(
            candidate_case_ids=candidate_case_ids,
            recent_same_case=recent_same_case,
        )
        recommended_actions = self._build_problem_dependency_actions(
            candidate_case_ids=candidate_case_ids,
            immediate_predecessor=immediate_predecessor,
            recent_same_case=recent_same_case,
        )

        return {
            "recent_predecessors": predecessor_payloads,
            "candidate_case_ids": candidate_case_ids,
            "recent_same_case": recent_same_case,
            "immediate_predecessor": immediate_predecessor,
            "signal_strength": signal_strength,
            "recommended_actions": recommended_actions,
        }

    def _classify_problem_dependency_signal(
        self,
        *,
        candidate_case_ids: list[str],
        recent_same_case: dict[str, Any] | None,
    ) -> str:
        has_candidates = bool(candidate_case_ids)
        has_same_case = recent_same_case is not None
        if has_candidates and has_same_case:
            return "sequence_and_repeat_history"
        if has_candidates:
            return "recent_sequence"
        if has_same_case:
            return "repeat_history"
        return "none"

    def _build_problem_dependency_actions(
        self,
        *,
        candidate_case_ids: list[str],
        immediate_predecessor: dict[str, Any] | None,
        recent_same_case: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        if immediate_predecessor is not None:
            actions.append(
                {
                    "priority": "high",
                    "action": "inspect_immediate_predecessor",
                    "case_id": immediate_predecessor.get("case_id"),
                    "execution_id": immediate_predecessor.get("execution_id"),
                    "reason": "review the case that ran immediately before the preserved failure",
                }
            )
        if candidate_case_ids:
            actions.append(
                {
                    "priority": "high",
                    "action": "rerun_candidate_predecessors_before_replay",
                    "case_ids": candidate_case_ids,
                    "reason": "rerun the recent predecessor cases before replaying again to check for stateful dependencies",
                }
            )
        if recent_same_case is not None:
            actions.append(
                {
                    "priority": "medium",
                    "action": "compare_recent_same_case",
                    "case_id": recent_same_case.get("case_id"),
                    "execution_id": recent_same_case.get("execution_id"),
                    "reason": "compare the preserved failure with the most recent execution of the same case",
                }
            )
        return actions

    def _extract_problem_latest_comparison(
        self, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        metadata = payload.get("metadata", {})
        if not isinstance(metadata, dict):
            return None
        latest_recovery = metadata.get("latest_recovery", {})
        if not isinstance(latest_recovery, dict):
            return None
        if latest_recovery.get("action_type") != "replay":
            return None
        result = latest_recovery.get("result_summary", {})
        if not isinstance(result, dict) or not result:
            result = latest_recovery.get("result", {})
        if not isinstance(result, dict):
            return None
        comparison = result.get("comparison")
        return comparison if isinstance(comparison, dict) else None

    def _build_problem_investigation_summary(
        self,
        payload: dict[str, Any],
        *,
        view: str,
        reproduction_summary: dict[str, Any] | None = None,
        comparison: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        problem_id = str(payload.get("problem_id", ""))
        capabilities = payload.get("capabilities", {})
        if not isinstance(capabilities, dict):
            capabilities = {}
        preservation = payload.get("preservation", {})
        if not isinstance(preservation, dict):
            preservation = {}
        investigation: dict[str, Any] = {
            "view": view,
            "problem_id": problem_id,
            "problem_type": payload.get("problem_type"),
            "summary": payload.get("summary"),
            "preservation_status": preservation.get("status"),
            "latest_action": payload.get("latest_action"),
            "capabilities": {
                "can_replay": capabilities.get("can_replay"),
                "can_recover": capabilities.get("can_recover"),
                "replay_mode": capabilities.get("replay_mode"),
                "recover_mode": capabilities.get("recover_mode"),
            },
            "recommended_commands": self._build_problem_recommended_commands(
                problem_id
            ),
        }
        runtime_backend = payload.get("runtime_backend", {})
        if isinstance(runtime_backend, dict) and runtime_backend:
            investigation["runtime_backend"] = runtime_backend
        details = payload.get("details", {})
        if isinstance(details, dict):
            object_artifacts = details.get("object_artifacts", {})
            if isinstance(object_artifacts, dict) and object_artifacts:
                investigation["object_artifacts"] = object_artifacts
        if payload.get("problem_type") == "data_state":
            data_investigation = self._build_data_state_investigation_summary(payload)
            investigation.update(data_investigation)
        if payload.get("problem_type") == "service_runtime":
            runtime_investigation = self._build_service_runtime_investigation_summary(
                payload
            )
            investigation.update(runtime_investigation)
        if payload.get("problem_type") == "crash_dump":
            crash_investigation = self._build_crash_dump_investigation_summary(payload)
            investigation.update(crash_investigation)
        if isinstance(reproduction_summary, dict):
            request = reproduction_summary.get("request", {})
            if isinstance(request, dict):
                investigation["request"] = {
                    "method": request.get("method"),
                    "url": request.get("url"),
                }
            expected = reproduction_summary.get("expected", {})
            if isinstance(expected, dict):
                investigation["expected"] = expected
            dependency_hints = reproduction_summary.get("dependency_hints")
            if isinstance(dependency_hints, dict):
                investigation["dependency"] = self._build_problem_dependency_digest(
                    dependency_hints
                )
                investigation["next_actions"] = dependency_hints.get(
                    "recommended_actions", []
                )
        if isinstance(comparison, dict):
            boundary = comparison.get("boundary", {})
            if isinstance(boundary, dict):
                investigation["replay"] = {
                    "reproduced": comparison.get("expectation", {}).get("reproduced")
                    if isinstance(comparison.get("expectation"), dict)
                    else comparison.get("reproduced"),
                    "assessment": boundary.get("assessment"),
                    "scope": boundary.get("scope"),
                    "confidence": boundary.get("confidence"),
                    "hidden_dependency_possible": boundary.get(
                        "hidden_dependency_possible"
                    ),
                }
                dependency_hints = boundary.get("dependency_hints")
                if isinstance(dependency_hints, dict):
                    investigation["dependency"] = self._build_problem_dependency_digest(
                        dependency_hints
                    )
                recommended_actions = boundary.get("recommended_actions")
                if isinstance(recommended_actions, list):
                    investigation["next_actions"] = recommended_actions
        workspace_recovery = self._build_workspace_recovery_plan(
            problem_id=problem_id,
            problem_type=str(payload.get("problem_type", "")),
            object_refs=payload.get("object_refs", [])
            if isinstance(payload.get("object_refs"), list)
            else [],
            details=payload.get("details", {})
            if isinstance(payload.get("details"), dict)
            else {},
            recovery=payload.get("recovery", {})
            if isinstance(payload.get("recovery"), dict)
            else {},
        )
        investigation["workspace_recovery"] = workspace_recovery
        side_effect_hints = self._build_problem_side_effect_hints(
            problem_type=str(payload.get("problem_type", "")),
            execution_id=str(payload.get("execution_id", "")),
            case_id=str(payload.get("case_id", "")),
            details=payload.get("details", {})
            if isinstance(payload.get("details"), dict)
            else {},
            recovery=payload.get("recovery", {})
            if isinstance(payload.get("recovery"), dict)
            else {},
        )
        if side_effect_hints:
            investigation["side_effect"] = self._build_problem_side_effect_digest(
                side_effect_hints
            )
            investigation["environment_recovery"] = (
                self._build_environment_recovery_from_side_effect(
                    problem_type=str(payload.get("problem_type", "")),
                    side_effect_hints=side_effect_hints,
                    workspace_recovery=workspace_recovery,
                )
            )
        investigation.setdefault("next_actions", [])
        investigation["diagnostics"] = self._build_problem_diagnostics_summary(
            payload,
            investigation=investigation,
        )
        return investigation

    def _build_problem_diagnostics_summary(
        self,
        payload: dict[str, Any],
        *,
        investigation: dict[str, Any],
    ) -> dict[str, Any]:
        object_refs = [
            str(item)
            for item in payload.get("object_refs", [])
            if isinstance(item, str) and item
        ]
        runtime_backend = payload.get("runtime_backend", {})
        if not isinstance(runtime_backend, dict):
            runtime_backend = {}
        details = payload.get("details", {})
        if not isinstance(details, dict):
            details = {}
        object_artifacts = details.get("object_artifacts", {})
        if not isinstance(object_artifacts, dict):
            object_artifacts = investigation.get("object_artifacts", {})
        object_artifacts_summary: dict[str, Any] = {}
        artifact_refs: dict[str, Any] = {}
        if isinstance(object_artifacts, dict) and object_artifacts:
            artifact_ref = object_artifacts.get("artifact_ref")
            if isinstance(artifact_ref, str) and artifact_ref:
                artifact_refs["object_artifacts"] = artifact_ref
            object_artifacts_summary = self._summarize_object_artifacts(
                object_artifacts,
                artifact_ref=artifact_ref if isinstance(artifact_ref, str) else None,
            )
        execution_id = payload.get("execution_id")
        if isinstance(execution_id, str) and execution_id:
            artifact_refs["execution"] = execution_id
        signals = self._build_diagnostic_signals(
            runtime_backend=runtime_backend,
            object_artifacts_summary=object_artifacts_summary,
        )
        has_runtime = bool(runtime_backend)
        has_object_artifacts = bool(object_artifacts_summary)
        if has_runtime and (has_object_artifacts or not object_refs):
            status = "complete"
        elif has_runtime or has_object_artifacts or object_refs:
            status = "partial"
        else:
            status = "unavailable"
        diagnostics: dict[str, Any] = {
            "status": status,
            "object_refs": object_refs,
            "signals": signals,
            "next_views": self._build_diagnostic_next_views(
                problem_id=str(payload.get("problem_id", "")),
                execution_id=execution_id if isinstance(execution_id, str) else "",
                object_refs=object_refs,
            ),
        }
        if runtime_backend:
            diagnostics["runtime_backend"] = runtime_backend
        if object_artifacts_summary:
            diagnostics["object_artifacts"] = object_artifacts_summary
        if artifact_refs:
            diagnostics["artifact_refs"] = artifact_refs
        return diagnostics

    def _build_object_status_diagnostics(
        self,
        record: ManagedObjectRecord,
        *,
        linked_problems: list[dict[str, Any]],
    ) -> dict[str, Any]:
        metadata = record.metadata if isinstance(record.metadata, dict) else {}
        runtime_backend = metadata.get("runtime_backend", {})
        if not isinstance(runtime_backend, dict) or not runtime_backend:
            runtime_backend = self._build_object_runtime_backend_summary(record)
        runtime = metadata.get("runtime", {})
        if not isinstance(runtime, dict):
            runtime = {}
        managed_instance = self._build_managed_instance_diagnostics(record)
        runtime_preflight: dict[str, Any] | None = None
        preflight_meta = metadata.get("runtime_preflight", {})
        if isinstance(preflight_meta, dict):
            last_check = preflight_meta.get("last_check")
            if isinstance(last_check, dict):
                runtime_preflight = last_check
        if runtime_preflight is None and self._supports_runtime_preflight(record):
            try:
                runtime_preflight = self._build_object_runtime_preflight(record)
            except Exception:
                runtime_preflight = None
        diagnostics: dict[str, Any] = {
            "status": "complete" if runtime_backend else "partial",
            "runtime_backend": runtime_backend,
            "runtime": runtime,
            "managed_instance": managed_instance,
            "recent_problems": linked_problems,
            "problem_summary": self._build_object_problem_summary(record.name),
            "signals": self._build_object_status_diagnostic_signals(
                record,
                runtime_backend=runtime_backend,
                managed_instance=managed_instance,
                linked_problems=linked_problems,
                runtime_preflight=runtime_preflight,
            ),
            "suggested_views": self._build_diagnostic_next_views(
                problem_id=str(linked_problems[0]["problem_id"])
                if linked_problems
                else "",
                execution_id="",
                object_refs=[record.name],
            ),
        }
        if runtime_preflight is not None:
            diagnostics["runtime_preflight"] = runtime_preflight
        return diagnostics

    def _build_managed_instance_diagnostics(
        self,
        record: ManagedObjectRecord,
    ) -> dict[str, Any]:
        config = record.config if isinstance(record.config, dict) else {}
        managed_instance = config.get("managed_instance", {})
        if not isinstance(managed_instance, dict) or not managed_instance:
            return {"available": False, "reason": "managed_instance_not_configured"}
        paths: dict[str, Any] = {}
        for key, value in sorted(managed_instance.items()):
            if not isinstance(value, str) or not value:
                continue
            path = Path(value).expanduser()
            try:
                exists = path.exists()
                kind = (
                    "directory"
                    if path.is_dir()
                    else "file"
                    if path.is_file()
                    else "path"
                )
                paths[key] = {
                    "path": self._workspace_display_path(path),
                    "exists": exists,
                    "kind": kind,
                }
            except OSError as exc:
                paths[key] = {
                    "path": self._workspace_display_path(path),
                    "exists": False,
                    "error": str(exc),
                }
        return {
            "available": bool(paths),
            "paths": paths,
        }

    def _build_object_status_diagnostic_signals(
        self,
        record: ManagedObjectRecord,
        *,
        runtime_backend: dict[str, Any],
        managed_instance: dict[str, Any],
        linked_problems: list[dict[str, Any]],
        runtime_preflight: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        signals = self._runtime_backend_diagnostic_signals(
            runtime_backend,
            object_name=record.name,
        )
        if is_failure_preserved_object_status(record.status):
            signals.append(
                {
                    "level": "warning",
                    "code": "object_failure_preserved",
                    "message": f"object is preserved in failure state '{record.status}'",
                    "object_name": record.name,
                }
            )
        if linked_problems:
            signals.append(
                {
                    "level": "info",
                    "code": "recent_problem_linked",
                    "message": "object has recent linked problem records",
                    "object_name": record.name,
                    "problem_id": linked_problems[0].get("problem_id"),
                }
            )
        paths = managed_instance.get("paths", {})
        if isinstance(paths, dict):
            for key, item in paths.items():
                if isinstance(item, dict) and item.get("exists") is False:
                    signals.append(
                        {
                            "level": "warning",
                            "code": "managed_instance_missing",
                            "message": f"managed instance path '{key}' is missing",
                            "object_name": record.name,
                        }
                    )
        if isinstance(runtime_preflight, dict):
            preflight_status = runtime_preflight.get("status")
            if preflight_status == "failed":
                signals.append(
                    {
                        "level": "error",
                        "code": "runtime_preflight_failed",
                        "message": "runtime preflight check failed",
                        "object_name": record.name,
                    }
                )
            elif preflight_status == "warning":
                signals.append(
                    {
                        "level": "warning",
                        "code": "runtime_preflight_warning",
                        "message": "runtime preflight check has warnings",
                        "object_name": record.name,
                    }
                )
        return signals

    def _build_diagnostic_signals(
        self,
        *,
        runtime_backend: dict[str, Any],
        object_artifacts_summary: dict[str, Any],
    ) -> list[dict[str, Any]]:
        signals = self._runtime_backend_diagnostic_signals(runtime_backend)
        for item in object_artifacts_summary.get("objects", []):
            if not isinstance(item, dict):
                continue
            object_name = item.get("object_name")
            if item.get("object_found") is False:
                signals.append(
                    {
                        "level": "warning",
                        "code": "object_missing",
                        "message": "object referenced by diagnostics was not found",
                        "object_name": object_name,
                    }
                )
            if item.get("status_changed") is True:
                signals.append(
                    {
                        "level": "info",
                        "code": "object_status_changed",
                        "message": "object status changed during execution",
                        "object_name": object_name,
                        "before_status": item.get("before_status"),
                        "after_status": item.get("after_status"),
                    }
                )
        if object_artifacts_summary.get("available") is False:
            signals.append(
                {
                    "level": "warning",
                    "code": "object_artifacts_unavailable",
                    "message": "object artifacts summary is unavailable",
                }
            )
        return signals

    def _runtime_backend_diagnostic_signals(
        self,
        runtime_backend: dict[str, Any],
        *,
        object_name: str | None = None,
    ) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []
        backend_items = self._get_runtime_backend_items(runtime_backend)
        for backend_item in backend_items:
            current_object_name = object_name or backend_item.get("object_name")
            backend = backend_item.get("runtime_backend", backend_item)
            if not isinstance(backend, dict):
                continue
            if backend.get("capability_status") == "unsatisfied":
                signal: dict[str, Any] = {
                    "level": "error",
                    "code": "runtime_backend_unsatisfied",
                    "message": "runtime backend does not satisfy required capabilities",
                }
                if isinstance(current_object_name, str) and current_object_name:
                    signal["object_name"] = current_object_name
                signals.append(signal)
            preflight = backend.get("last_preflight", {})
            if isinstance(preflight, dict) and preflight.get("status") == "failed":
                signal = {
                    "level": "error",
                    "code": "runtime_backend_preflight_failed",
                    "message": "runtime backend preflight failed",
                    "failure_reason": preflight.get("failure_reason"),
                }
                if isinstance(current_object_name, str) and current_object_name:
                    signal["object_name"] = current_object_name
                signals.append(signal)
        return signals

    def _get_runtime_backend_items(
        self,
        runtime_backend: dict[str, Any],
    ) -> list[dict[str, Any]]:
        objects = runtime_backend.get("objects", [])
        if isinstance(objects, list):
            return [item for item in objects if isinstance(item, dict)]
        if runtime_backend:
            return [runtime_backend]
        return []

    def _build_diagnostic_next_views(
        self,
        *,
        problem_id: str,
        execution_id: str,
        object_refs: list[str],
    ) -> list[dict[str, Any]]:
        views: list[dict[str, Any]] = []
        if problem_id:
            views.append(
                {
                    "view": "problem_assets",
                    "command": f"ptest problem assets {problem_id}",
                    "reason": "inspect preserved problem assets",
                }
            )
        if execution_id:
            views.append(
                {
                    "view": "execution_artifacts",
                    "command": f"ptest execution artifacts {execution_id}",
                    "reason": "inspect execution artifact index and object artifacts",
                }
            )
        for object_name in object_refs[:3]:
            views.append(
                {
                    "view": "object_status",
                    "command": f"ptest obj status {object_name}",
                    "reason": "inspect current object runtime status",
                    "object_name": object_name,
                }
            )
        return views

    def _build_data_state_investigation_summary(
        self, payload: dict[str, Any]
    ) -> dict[str, Any]:
        details = payload.get("details", {})
        if not isinstance(details, dict):
            details = {}
        recovery = payload.get("recovery", {})
        if not isinstance(recovery, dict):
            recovery = {}
        data_source = details.get("data_source", {})
        if not isinstance(data_source, dict):
            data_source = {}
        failure_kind = recovery.get("failure_kind", details.get("failure_kind"))
        state_hints = recovery.get("state_hints", details.get("state_hints", {}))
        origin_hints = recovery.get("origin_hints", details.get("origin_hints", {}))
        boundary = recovery.get("boundary", {})
        next_actions = recovery.get("next_actions", [])
        summary: dict[str, Any] = {
            "data_source": {
                "db_type": data_source.get("db_type"),
                "database": data_source.get("database"),
                "host": data_source.get("host"),
                "port": data_source.get("port"),
            },
            "failure_kind": failure_kind,
            "state_hints": state_hints if isinstance(state_hints, dict) else {},
        }
        if isinstance(origin_hints, dict):
            summary["origin_hints"] = {
                "classification": origin_hints.get("classification"),
                "query_context": origin_hints.get("query_context"),
                "signal_strength": origin_hints.get("signal_strength"),
                "candidate_case_ids": origin_hints.get("candidate_case_ids", []),
                "immediate_predecessor": origin_hints.get("immediate_predecessor"),
                "recent_same_case": origin_hints.get("recent_same_case"),
            }
        if isinstance(boundary, dict):
            summary["boundary"] = {
                "scope": boundary.get("scope"),
                "confidence": boundary.get("confidence"),
                "assessment": boundary.get("assessment"),
                "reason": boundary.get("reason"),
                "needs_historical_state": boundary.get("needs_historical_state"),
            }
        if isinstance(next_actions, list):
            summary["next_actions"] = next_actions
        data_state_artifacts = details.get("data_state_artifacts")
        summary["state_snapshot"] = self._summarize_data_state_artifacts(
            data_state_artifacts
        )
        return summary

    def _build_crash_dump_object_summary(self, service_name: Any) -> dict[str, Any]:
        if not isinstance(service_name, str) or not service_name:
            return {
                "service_name": service_name,
                "object_found": False,
            }
        record = self.storage.get_object(service_name)
        if record is None:
            return {
                "service_name": service_name,
                "object_found": False,
            }
        crash_capture = (
            record.metadata.get("crash_capture", {})
            if isinstance(record.metadata, dict)
            else {}
        )
        if not isinstance(crash_capture, dict):
            crash_capture = {}
        return {
            "service_name": service_name,
            "object_found": True,
            "type_name": record.type_name,
            "status": record.status,
            "installed": record.installed,
            "updated_at": record.updated_at,
            "dump_dir": crash_capture.get("dump_dir"),
        }

    def _build_crash_dump_log_window(self, log_refs: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(log_refs, dict):
            return {
                "workspace_logs_dir": None,
                "file_count": 0,
                "latest_files": [],
                "snippets": [],
            }
        workspace_logs_dir = log_refs.get("workspace_logs_dir")
        files = log_refs.get("files", [])
        latest_files = files if isinstance(files, list) else []
        latest_files = latest_files[-2:]
        snippets: list[dict[str, Any]] = []
        if isinstance(workspace_logs_dir, str) and workspace_logs_dir:
            for item in latest_files:
                if not isinstance(item, dict):
                    continue
                relative_path = item.get("path")
                if not isinstance(relative_path, str) or not relative_path:
                    continue
                log_path = (self.root_path / relative_path).resolve()
                if not log_path.exists() or not log_path.is_file():
                    continue
                try:
                    lines = log_path.read_text(
                        encoding="utf-8", errors="replace"
                    ).splitlines()
                except OSError:
                    continue
                snippets.append(
                    {
                        "path": relative_path,
                        "tail": lines[-8:],
                    }
                )
        return {
            "workspace_logs_dir": workspace_logs_dir
            if isinstance(workspace_logs_dir, str)
            else None,
            "file_count": len(files) if isinstance(files, list) else 0,
            "latest_files": latest_files,
            "snippets": snippets,
        }

    def _build_service_runtime_investigation_summary(
        self, payload: dict[str, Any]
    ) -> dict[str, Any]:
        details = payload.get("details", {})
        if not isinstance(details, dict):
            details = {}
        recovery = payload.get("recovery", {})
        if not isinstance(recovery, dict):
            recovery = {}
        service = details.get("service", {})
        if not isinstance(service, dict):
            service = {}
        runtime_result = details.get("runtime_result", {})
        if not isinstance(runtime_result, dict):
            runtime_result = {}
        failure_kind = recovery.get("failure_kind", details.get("failure_kind"))
        runtime_hints = recovery.get("runtime_hints", details.get("runtime_hints", {}))
        boundary = recovery.get("boundary", {})
        next_actions = recovery.get("next_actions", [])
        summary: dict[str, Any] = {
            "runtime_target": {
                "service_name": service.get("service_name"),
                "object_name": service.get("service_name"),
                "runtime_backend": "object_or_external_service",
                "host": service.get("host"),
                "port": service.get("port"),
            },
            "failure_kind": failure_kind,
            "runtime_status": runtime_result.get("status"),
        }
        if isinstance(runtime_hints, dict):
            summary["runtime_hints"] = {
                "object_status": runtime_hints.get("object_status"),
                "check_type": runtime_hints.get("check_type"),
                "connectable": runtime_hints.get("connectable"),
                "expected_runtime_state": runtime_hints.get("expected_runtime_state"),
                "error_keywords": runtime_hints.get("error_keywords", []),
            }
        if isinstance(boundary, dict):
            summary["boundary"] = {
                "scope": boundary.get("scope"),
                "confidence": boundary.get("confidence"),
                "assessment": boundary.get("assessment"),
                "reason": boundary.get("reason"),
                "needs_runtime_history": boundary.get("needs_runtime_history"),
            }
        if isinstance(next_actions, list):
            summary["next_actions"] = next_actions
        return summary

    def _build_crash_dump_investigation_summary(
        self, payload: dict[str, Any]
    ) -> dict[str, Any]:
        details = payload.get("details", {})
        if not isinstance(details, dict):
            details = {}
        recovery = payload.get("recovery", {})
        if not isinstance(recovery, dict):
            recovery = {}
        crash_target = details.get("crash_target", {})
        if not isinstance(crash_target, dict):
            crash_target = {}
        crash_event = details.get("crash_event", {})
        if not isinstance(crash_event, dict):
            crash_event = {}
        dump_refs = recovery.get("dump_refs", details.get("dump_refs", []))
        boundary = recovery.get("boundary", {})
        next_actions = recovery.get("next_actions", [])
        summary: dict[str, Any] = {
            "crash_target": crash_target,
            "crash_summary": {
                "execution_status": crash_event.get("execution_status"),
                "detected_at": crash_event.get("detected_at"),
                "error": crash_event.get("error"),
            },
            "dump_refs": dump_refs if isinstance(dump_refs, list) else [],
        }
        if isinstance(boundary, dict):
            summary["boundary"] = {
                "scope": boundary.get("scope"),
                "confidence": boundary.get("confidence"),
                "assessment": boundary.get("assessment"),
                "reason": boundary.get("reason"),
                "needs_dump_analysis": boundary.get("needs_dump_analysis"),
            }
        if isinstance(next_actions, list):
            summary["next_actions"] = next_actions
        object_summary = recovery.get(
            "object_summary", details.get("object_summary", {})
        )
        if isinstance(object_summary, dict):
            summary["object_summary"] = object_summary
        log_window = recovery.get("log_window", details.get("log_window", {}))
        if isinstance(log_window, dict):
            summary["log_window"] = {
                "workspace_logs_dir": log_window.get("workspace_logs_dir"),
                "file_count": log_window.get("file_count"),
                "latest_files": log_window.get("latest_files", []),
                "snippets": log_window.get("snippets", []),
            }
        return summary

    def _build_problem_dependency_digest(
        self, dependency_hints: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "signal_strength": dependency_hints.get("signal_strength", "none"),
            "candidate_case_ids": dependency_hints.get("candidate_case_ids", []),
            "immediate_predecessor": dependency_hints.get("immediate_predecessor"),
            "recent_same_case": dependency_hints.get("recent_same_case"),
            "recommended_actions": dependency_hints.get("recommended_actions", []),
        }

    def _build_problem_side_effect_hints(
        self,
        *,
        problem_type: str,
        execution_id: str,
        case_id: str,
        details: dict[str, Any],
        recovery: dict[str, Any],
    ) -> dict[str, Any]:
        if problem_type not in {
            "api_response",
            "service_runtime",
            "data_state",
            "crash_dump",
        }:
            return {}

        dependency_hints = self._build_problem_dependency_hints(
            execution_id=execution_id,
            case_id=case_id,
        )
        signal_strength = str(dependency_hints.get("signal_strength", "none"))
        candidate_case_ids = dependency_hints.get("candidate_case_ids", [])
        immediate_predecessor = dependency_hints.get("immediate_predecessor")
        environment_shift_detected = signal_strength != "none" and (
            bool(candidate_case_ids) or isinstance(immediate_predecessor, dict)
        )
        likely_trigger_case_id = (
            immediate_predecessor.get("case_id")
            if isinstance(immediate_predecessor, dict)
            else None
        )

        if environment_shift_detected:
            if problem_type == "api_response":
                classification = "possible_request_side_effect"
                reason = (
                    "recent preceding cases may have changed remote service state "
                    "before the preserved request failed"
                )
            elif problem_type == "data_state":
                classification = "possible_data_pollution"
                reason = (
                    "recent preceding cases may have changed persisted data state "
                    "before the preserved query failed"
                )
            elif problem_type == "crash_dump":
                classification = "possible_crash_inducing_side_effect"
                reason = (
                    "recent preceding cases may have destabilized the target "
                    "service before the preserved crash dump was captured"
                )
            else:
                classification = "possible_runtime_destabilization"
                reason = (
                    "recent preceding cases may have destabilized the target "
                    "service before the preserved runtime check failed"
                )
        else:
            classification = "no_recent_side_effect_signal"
            reason = (
                "no recent execution sequence strongly suggests a prior test-side "
                "effect for the preserved failure"
            )

        return {
            **dependency_hints,
            "classification": classification,
            "environment_shift_detected": environment_shift_detected,
            "likely_trigger_case_id": likely_trigger_case_id,
            "reason": reason,
            "problem_scope": problem_type,
            "runtime_failure_kind": recovery.get("failure_kind")
            if problem_type == "service_runtime"
            else None,
            "crash_target_service_name": details.get("crash_target", {}).get(
                "service_name"
            )
            if problem_type == "crash_dump"
            and isinstance(details.get("crash_target"), dict)
            else None,
            "request_url": details.get("request", {}).get("url")
            if isinstance(details.get("request"), dict)
            else None,
        }

    def _build_problem_side_effect_digest(
        self, side_effect_hints: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "classification": side_effect_hints.get("classification"),
            "signal_strength": side_effect_hints.get("signal_strength", "none"),
            "environment_shift_detected": side_effect_hints.get(
                "environment_shift_detected", False
            ),
            "likely_trigger_case_id": side_effect_hints.get("likely_trigger_case_id"),
            "candidate_case_ids": side_effect_hints.get("candidate_case_ids", []),
            "immediate_predecessor": side_effect_hints.get("immediate_predecessor"),
            "reason": side_effect_hints.get("reason"),
        }

    def _build_environment_recovery_from_side_effect(
        self,
        *,
        problem_type: str,
        side_effect_hints: dict[str, Any],
        workspace_recovery: dict[str, Any],
    ) -> dict[str, Any]:
        signal_strength = str(side_effect_hints.get("signal_strength", "none"))
        environment_shift_detected = bool(
            side_effect_hints.get("environment_shift_detected", False)
        )
        likely_trigger_case_id = side_effect_hints.get("likely_trigger_case_id")
        confidence = {
            "recent_sequence": "medium_for_recent_sequence_signal",
            "same_case_history": "low_for_same_case_history_only",
        }.get(signal_strength, "low_when_side_effect_signal_is_sparse")
        assessment = (
            "environment_may_have_shifted_by_prior_case"
            if environment_shift_detected
            else "no_prior_side_effect_signal_detected"
        )
        recommended_sequence: list[str] = []
        if isinstance(likely_trigger_case_id, str) and likely_trigger_case_id:
            recommended_sequence.append("inspect_likely_trigger_case_effects")
        workspace_sequence = workspace_recovery.get("recommended_sequence", [])
        if isinstance(workspace_sequence, list):
            recommended_sequence.extend(
                str(item) for item in workspace_sequence if isinstance(item, str)
            )
        recommended_sequence.append("rerun_affected_case_after_baseline_restore")
        return {
            "scope": "workspace_side_effect_minimum_recovery",
            "assessment": assessment,
            "confidence": confidence,
            "problem_scope": problem_type,
            "likely_trigger_case_id": likely_trigger_case_id,
            "affected_objects": workspace_recovery.get("affected_objects", []),
            "recommended_sequence": recommended_sequence,
            "reason": side_effect_hints.get("reason"),
            "recovery_boundary": {
                "scope": "workspace_side_effect_minimum_recovery",
                "does_not_cover": [
                    "automatic_environment_rollback",
                    "snapshot_restore",
                    "container_level_recovery",
                    "multi_service_side_effect_recovery",
                ],
            },
        }

    def _build_problem_recommended_commands(self, problem_id: str) -> list[str]:
        if not problem_id:
            return []
        return [
            f"ptest problem show {problem_id}",
            f"ptest problem assets {problem_id}",
            f"ptest problem replay {problem_id}",
        ]

    def _build_api_replay_header_summary(
        self, replay_response: dict[str, Any]
    ) -> dict[str, Any]:
        replay_headers = replay_response.get("headers", {})
        if not isinstance(replay_headers, dict):
            replay_headers = {}
        header_names = sorted(str(key) for key in replay_headers.keys())
        return {
            "comparable": False,
            "reason": "preserved response headers are not available in the current problem record",
            "replay_header_count": len(header_names),
            "replay_header_names": header_names,
        }

    def _build_api_replay_body_summary(
        self,
        *,
        preserved_body: Any,
        replay_body: Any,
        response_body_changed: bool | None,
    ) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "comparable": preserved_body is not None,
            "changed": response_body_changed,
            "preserved_type": self._problem_value_type_name(preserved_body),
            "replay_type": self._problem_value_type_name(replay_body),
            "change_kind": "preserved_body_unavailable",
            "preserved_preview": self._problem_value_preview(preserved_body),
            "replay_preview": self._problem_value_preview(replay_body),
        }
        if preserved_body is None:
            return summary
        if response_body_changed is False:
            summary["change_kind"] = "same"
            return summary
        if type(preserved_body) is not type(replay_body):
            summary["change_kind"] = "type_changed"
            return summary
        if isinstance(preserved_body, dict) and isinstance(replay_body, dict):
            preserved_keys = set(preserved_body.keys())
            replay_keys = set(replay_body.keys())
            changed_keys = sorted(
                key
                for key in preserved_keys & replay_keys
                if not self._compare_problem_values(
                    preserved_body[key], replay_body[key]
                )
            )
            summary["change_kind"] = "top_level_fields_changed"
            summary["added_top_level_fields"] = sorted(replay_keys - preserved_keys)
            summary["removed_top_level_fields"] = sorted(preserved_keys - replay_keys)
            summary["changed_top_level_fields"] = changed_keys
            return summary
        if isinstance(preserved_body, list) and isinstance(replay_body, list):
            summary["change_kind"] = "sequence_changed"
            summary["preserved_length"] = len(preserved_body)
            summary["replay_length"] = len(replay_body)
            return summary
        summary["change_kind"] = "value_changed"
        return summary

    def _problem_value_type_name(self, value: Any) -> str:
        if value is None:
            return "none"
        if isinstance(value, dict):
            return "object"
        if isinstance(value, list):
            return "array"
        if isinstance(value, str):
            return "string"
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, int | float):
            return "number"
        return type(value).__name__

    def _problem_value_preview(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, dict):
            preview: dict[str, Any] = {}
            for key in sorted(value.keys())[:3]:
                preview[str(key)] = self._problem_preview_leaf(value[key])
            return preview
        if isinstance(value, list):
            return [self._problem_preview_leaf(item) for item in value[:3]]
        return self._problem_preview_leaf(value)

    def _problem_preview_leaf(self, value: Any) -> Any:
        if isinstance(value, dict):
            return "{...}"
        if isinstance(value, list):
            return f"[... x{len(value)}]"
        return value

    def _build_problem_reproduction_summary(
        self, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        if payload.get("problem_type") != "api_response":
            return None
        details = payload.get("details", {})
        if not isinstance(details, dict):
            return None

        request = details.get("request", {})
        response = details.get("response", {})
        preservation = payload.get("preservation", {})
        if not isinstance(request, dict) or not isinstance(response, dict):
            return None
        if not isinstance(preservation, dict):
            preservation = {}

        expected = self._build_api_expected_summary(details)
        dependency_hints = self._build_problem_dependency_hints(
            execution_id=str(payload.get("execution_id", "")),
            case_id=str(payload.get("case_id", "")),
        )
        side_effect_hints = self._build_problem_side_effect_hints(
            problem_type="api_response",
            execution_id=str(payload.get("execution_id", "")),
            case_id=str(payload.get("case_id", "")),
            details=details,
            recovery=payload.get("recovery", {})
            if isinstance(payload.get("recovery"), dict)
            else {},
        )
        observed_failure = {
            "status_code": response.get("observed_status_code"),
            "body": response.get("observed_body"),
            "error": response.get("error"),
        }
        return {
            "problem_id": payload.get("problem_id"),
            "problem_type": payload.get("problem_type"),
            "case_id": payload.get("case_id"),
            "summary": payload.get("summary"),
            "request": {
                "method": request.get("method", "GET"),
                "url": request.get("url", ""),
                "headers": request.get("headers", {}),
                "params": request.get("params"),
                "body": request.get("body"),
            },
            "expected": expected,
            "observed_failure": observed_failure,
            "preservation": {
                "status": preservation.get("status"),
                "missing_assets": preservation.get("missing_assets", []),
            },
            "dependency_hints": dependency_hints,
            "side_effect_hints": side_effect_hints,
            "recommended_commands": self._build_problem_recommended_commands(
                str(payload.get("problem_id", ""))
            ),
        }

    def _build_api_expected_summary(self, details: dict[str, Any]) -> dict[str, Any]:
        response = details.get("response", {})
        case_payload = details.get("case", {})
        if not isinstance(response, dict):
            response = {}
        if not isinstance(case_payload, dict):
            case_payload = {}

        return {
            "status_code": response.get("expected_status"),
            "response_body": response.get("expected_response"),
            "assertions": case_payload.get("assertions", []),
        }

    def _build_recovery_plan(
        self, record: ProblemRecord, assets: ProblemAssetRecord
    ) -> dict[str, Any]:
        recovery_plan: dict[str, Any]
        if assets.problem_type == "api_response":
            recovery_plan = self._build_api_recovery_plan(record, assets)
        elif assets.problem_type == "data_state":
            recovery_plan = self._build_data_recovery_plan(record, assets)
        elif assets.problem_type in {
            "environment_init",
            "dependency_object",
            "dependency_configuration",
        }:
            recovery_plan = self._build_environment_dependency_recovery_plan(
                record, assets
            )
        elif assets.problem_type == "service_runtime":
            recovery_plan = self._build_service_runtime_recovery_plan(record, assets)
        elif assets.problem_type == "crash_dump":
            recovery_plan = self._build_crash_dump_recovery_plan(record, assets)
        else:
            recovery = assets.recovery if isinstance(assets.recovery, dict) else {}
            recovery_plan = {
                "problem_id": record.problem_id,
                "problem_type": record.problem_type,
                "summary": record.summary,
                "supported": bool(recovery.get("supported", False)),
                "mode": recovery.get("mode", "unsupported"),
                "steps": [],
                "hints": recovery,
            }

        recovery_plan["workspace_recovery"] = self._build_workspace_recovery_plan(
            problem_id=record.problem_id,
            problem_type=record.problem_type,
            object_refs=record.object_refs,
            details=assets.details if isinstance(assets.details, dict) else {},
            recovery=assets.recovery if isinstance(assets.recovery, dict) else {},
        )
        side_effect_hints = self._build_problem_side_effect_hints(
            problem_type=record.problem_type,
            execution_id=record.execution_id,
            case_id=record.case_id,
            details=assets.details if isinstance(assets.details, dict) else {},
            recovery=assets.recovery if isinstance(assets.recovery, dict) else {},
        )
        if side_effect_hints:
            recovery_plan["side_effect_hints"] = side_effect_hints
            recovery_plan["environment_recovery"] = (
                self._build_environment_recovery_from_side_effect(
                    problem_type=record.problem_type,
                    side_effect_hints=side_effect_hints,
                    workspace_recovery=recovery_plan["workspace_recovery"],
                )
            )
        return recovery_plan

    def _build_workspace_recovery_plan(
        self,
        *,
        problem_id: str,
        problem_type: str,
        object_refs: list[str],
        details: dict[str, Any],
        recovery: dict[str, Any],
    ) -> dict[str, Any]:
        affected_objects = self._build_workspace_recovery_affected_objects(
            problem_type=problem_type,
            object_refs=object_refs,
            details=details,
            recovery=recovery,
        )
        return {
            "scope": "workspace_minimum_recovery",
            "problem_id": problem_id,
            "affected_objects": affected_objects,
            "recommended_sequence": [
                item["object_name"]
                for item in affected_objects
                if isinstance(item.get("object_name"), str) and item.get("object_name")
            ],
            "recovery_boundary": {
                "scope": "workspace_minimum_recovery",
                "confidence": "minimal_object_level_plan",
                "assessment": "object_level_recovery_plan_only",
                "reason": "current workspace recovery summarizes minimal object actions only and does not execute them automatically",
                "does_not_cover": [
                    "automatic_recovery_execution",
                    "historical_state_snapshot_restore",
                    "container_level_recovery",
                    "cross_workspace_recovery",
                ],
            },
            "baseline_restore": self._build_workspace_baseline_restore_summary(),
            "post_recovery_checks": self._build_workspace_recovery_post_checks(
                problem_type=problem_type,
                problem_id=problem_id,
                affected_objects=affected_objects,
            ),
        }

    def _build_workspace_recovery_affected_objects(
        self,
        *,
        problem_type: str,
        object_refs: list[str],
        details: dict[str, Any],
        recovery: dict[str, Any],
    ) -> list[dict[str, Any]]:
        candidate_names: list[str] = []
        for raw_name in object_refs:
            if (
                isinstance(raw_name, str)
                and raw_name
                and raw_name not in candidate_names
            ):
                candidate_names.append(raw_name)

        inferred_names = [
            details.get("service", {}).get("service_name")
            if isinstance(details.get("service"), dict)
            else None,
            details.get("crash_target", {}).get("service_name")
            if isinstance(details.get("crash_target"), dict)
            else None,
            recovery.get("runtime_target", {}).get("object_name")
            if isinstance(recovery.get("runtime_target"), dict)
            else None,
            recovery.get("crash_target", {}).get("object_name")
            if isinstance(recovery.get("crash_target"), dict)
            else None,
        ]
        for inferred_name in inferred_names:
            if (
                isinstance(inferred_name, str)
                and inferred_name
                and inferred_name not in candidate_names
            ):
                candidate_names.append(inferred_name)

        affected_objects: list[dict[str, Any]] = []
        for object_name in candidate_names:
            record = self.storage.get_object(object_name)
            if record is None:
                affected_objects.append(
                    {
                        "object_name": object_name,
                        "object_found": False,
                        "recommended_action": "reinstall",
                        "reason": "the referenced object is not present in workspace state and should be recreated before deeper recovery",
                    }
                )
                continue
            recommended_action, reason = self._derive_workspace_recovery_action(
                problem_type=problem_type,
                status=record.status,
            )
            affected_objects.append(
                {
                    "object_name": object_name,
                    "object_found": True,
                    "type_name": record.type_name,
                    "current_status": record.status,
                    "installed": record.installed,
                    "recommended_action": recommended_action,
                    "reason": reason,
                }
            )
        return affected_objects

    def _derive_workspace_recovery_action(
        self, *, problem_type: str, status: str
    ) -> tuple[str, str]:
        if is_failure_preserved_object_status(status):
            return (
                "reinstall",
                "the object is already in a preserved failure state, so reinstall is the safest minimal recovery action",
            )
        if problem_type == "data_state":
            if status in {
                OBJECT_STATUS_RUNNING,
                OBJECT_STATUS_STOPPED,
                OBJECT_STATUS_INSTALLED,
            }:
                return (
                    "reset",
                    "data/state problems should first return the bound object to a clean minimal baseline before rerunning the preserved query",
                )
            if is_clearable_object_status(status):
                return (
                    "clear",
                    "the object can be cleared to remove residual state before rerunning validation",
                )
            return (
                "reinstall",
                "the object is not in a clean resettable state, so reinstall is the safer minimal fallback",
            )
        if problem_type in {"service_runtime", "crash_dump", "api_response"}:
            if status in {
                OBJECT_STATUS_RUNNING,
                OBJECT_STATUS_STOPPED,
                OBJECT_STATUS_INSTALLED,
            }:
                return (
                    "restart",
                    "the object should first be restarted to restore a known-good runtime baseline for follow-up checks",
                )
            if is_resettable_object_status(status):
                return (
                    "reset",
                    "the object can be reset to rebuild its minimal runnable state before further validation",
                )
            return (
                "reinstall",
                "the object is not in a stable runtime state, so reinstall is the safer minimal fallback",
            )
        if is_resettable_object_status(status):
            return (
                "reset",
                "the object supports reset and should be returned to a minimal baseline first",
            )
        return (
            "reinstall",
            "a minimal reinstall is the safest generic recovery action for the current object state",
        )

    def _build_workspace_baseline_summary(
        self, record: WorkspaceBaselineRecord
    ) -> dict[str, Any]:
        return {
            "baseline_id": record.baseline_id,
            "root_path": record.root_path,
            "summary": record.summary,
            "created_at": record.created_at,
            "object_count": len(record.objects)
            if isinstance(record.objects, list)
            else 0,
            "capture_scope": record.metadata.get("capture_scope")
            if isinstance(record.metadata, dict)
            else None,
            "object_reference_count": len(
                record.metadata.get("object_reference_snapshots", [])
            )
            if isinstance(record.metadata, dict)
            and isinstance(record.metadata.get("object_reference_snapshots"), list)
            else 0,
            "content_reference_count": len(
                record.metadata.get("content_reference_snapshots", [])
            )
            if isinstance(record.metadata, dict)
            and isinstance(record.metadata.get("content_reference_snapshots"), list)
            else 0,
            "limitations": record.metadata.get("limitations", [])
            if isinstance(record.metadata, dict)
            else [],
        }

    def _build_workspace_baseline_restore_summary(self) -> dict[str, Any]:
        baselines = self.storage.list_workspace_baselines()
        if not baselines:
            return {
                "available": False,
                "scope": "workspace_minimum_baseline_restore",
                "assessment": "no_workspace_baseline_available",
                "recommended_action": "create_workspace_baseline_before_heavier_recovery",
            }
        latest = baselines[0]
        return {
            "available": True,
            "scope": "workspace_minimum_baseline_restore",
            "assessment": "workspace_baseline_available_for_restore",
            "latest_baseline": self._build_workspace_baseline_summary(latest),
            "recommended_action": "restore_workspace_baseline_if_minimal_recovery_is_insufficient",
        }

    def _build_workspace_baseline_object_references(
        self, objects: dict[str, ManagedObjectRecord]
    ) -> list[dict[str, Any]]:
        references: list[dict[str, Any]] = []
        for record in objects.values():
            config = record.config if isinstance(record.config, dict) else {}
            managed_instance = (
                config.get("managed_instance", {})
                if isinstance(config.get("managed_instance"), dict)
                else {}
            )
            path_entries: list[dict[str, Any]] = []
            for field in (
                "instance_root",
                "install_dir",
                "data_dir",
                "config_dir",
                "log_dir",
                "run_dir",
                "dump_dir",
            ):
                raw_path = managed_instance.get(field)
                if isinstance(raw_path, str) and raw_path:
                    resolved = Path(raw_path).expanduser().resolve()
                    path_entries.append(
                        {
                            "field": field,
                            "path": str(resolved),
                            "exists": resolved.exists(),
                        }
                    )
            if path_entries:
                references.append(
                    {
                        "object_name": record.name,
                        "type_name": record.type_name,
                        "paths": path_entries,
                    }
                )
        return references

    def _restore_workspace_baseline_object_references(
        self, record: WorkspaceBaselineRecord
    ) -> dict[str, Any]:
        metadata = record.metadata if isinstance(record.metadata, dict) else {}
        snapshots = (
            metadata.get("object_reference_snapshots", [])
            if isinstance(metadata.get("object_reference_snapshots"), list)
            else []
        )
        restored_paths: list[dict[str, Any]] = []
        skipped_paths: list[dict[str, Any]] = []
        for item in snapshots:
            if not isinstance(item, dict):
                continue
            object_name = str(item.get("object_name", ""))
            for path_entry in item.get("paths", []):
                if not isinstance(path_entry, dict):
                    continue
                raw_path = path_entry.get("path")
                if not isinstance(raw_path, str) or not raw_path:
                    continue
                field = str(path_entry.get("field", ""))
                target = Path(raw_path).expanduser().resolve()
                try:
                    target.mkdir(parents=True, exist_ok=True)
                    restored_paths.append(
                        {
                            "object_name": object_name,
                            "field": field,
                            "path": str(target),
                        }
                    )
                except OSError as exc:
                    skipped_paths.append(
                        {
                            "object_name": object_name,
                            "field": field,
                            "path": str(target),
                            "reason": str(exc),
                        }
                    )
        return {
            "scope": "workspace_object_reference_restore",
            "restored_paths": restored_paths,
            "skipped_paths": skipped_paths,
            "limitations": [
                "directory existence is restored but directory contents are not replayed",
                "full data image restoration is not included in this stage",
            ],
        }

    def _build_workspace_baseline_content_snapshots(
        self,
        baseline_id: str,
        objects: dict[str, ManagedObjectRecord],
    ) -> dict[str, Any]:
        snapshots: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        workspace_root = self.root_path.resolve()
        for record in objects.values():
            config = record.config if isinstance(record.config, dict) else {}
            managed_instance = (
                config.get("managed_instance", {})
                if isinstance(config.get("managed_instance"), dict)
                else {}
            )
            for candidate in self._iter_workspace_baseline_content_candidates(
                record,
                managed_instance,
            ):
                source = candidate["path"]
                field = candidate["field"]
                relative_path = candidate["relative_path"]
                if len(snapshots) >= self.WORKSPACE_BASELINE_CONTENT_MAX_FILES:
                    skipped.append(
                        self._build_workspace_baseline_content_skip(
                            record,
                            field,
                            source,
                            "maximum_content_snapshot_file_count_reached",
                        )
                    )
                    continue
                if not source.is_relative_to(workspace_root):
                    skipped.append(
                        self._build_workspace_baseline_content_skip(
                            record,
                            field,
                            source,
                            "outside_workspace_not_supported",
                        )
                    )
                    continue
                if source.is_symlink():
                    skipped.append(
                        self._build_workspace_baseline_content_skip(
                            record,
                            field,
                            source,
                            "symlink_not_supported",
                        )
                    )
                    continue
                try:
                    size_bytes = source.stat().st_size
                except OSError as exc:
                    skipped.append(
                        self._build_workspace_baseline_content_skip(
                            record,
                            field,
                            source,
                            str(exc),
                        )
                    )
                    continue
                if size_bytes > self.WORKSPACE_BASELINE_CONTENT_MAX_BYTES:
                    skipped.append(
                        self._build_workspace_baseline_content_skip(
                            record,
                            field,
                            source,
                            "file_too_large_for_minimum_content_snapshot",
                        )
                    )
                    continue
                stored_relative_path = (
                    Path(baseline_id)
                    / "content"
                    / self._safe_workspace_baseline_path_segment(record.name)
                    / field
                    / relative_path
                )
                stored_path = self.storage.baselines_dir / stored_relative_path
                try:
                    stored_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, stored_path)
                    snapshots.append(
                        {
                            "object_name": record.name,
                            "type_name": record.type_name,
                            "field": field,
                            "path": str(source),
                            "relative_path": relative_path.as_posix(),
                            "stored_path": stored_relative_path.as_posix(),
                            "size_bytes": size_bytes,
                            "sha256": self._sha256_file(source),
                        }
                    )
                except OSError as exc:
                    skipped.append(
                        self._build_workspace_baseline_content_skip(
                            record,
                            field,
                            source,
                            str(exc),
                        )
                    )
        return {
            "scope": "workspace_content_reference_snapshot",
            "snapshots": snapshots,
            "skipped": skipped,
            "max_file_bytes": self.WORKSPACE_BASELINE_CONTENT_MAX_BYTES,
            "max_files": self.WORKSPACE_BASELINE_CONTENT_MAX_FILES,
        }

    def _iter_workspace_baseline_content_candidates(
        self,
        record: ManagedObjectRecord,
        managed_instance: dict[str, Any],
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        fields = ["config_dir"]
        if record.type_name.lower() in {"sqlite", "database"}:
            fields.append("data_dir")
        for field in fields:
            raw_path = managed_instance.get(field)
            if not isinstance(raw_path, str) or not raw_path:
                continue
            root = Path(raw_path).expanduser().resolve()
            if root.is_file():
                if self._is_supported_workspace_baseline_content_file(
                    record,
                    field,
                    root,
                ):
                    candidates.append(
                        {"field": field, "path": root, "relative_path": Path(root.name)}
                    )
                continue
            if not root.is_dir():
                continue
            for path in sorted(root.rglob("*")):
                if not path.is_file():
                    continue
                source = path.resolve()
                if not self._is_supported_workspace_baseline_content_file(
                    record,
                    field,
                    source,
                ):
                    continue
                try:
                    relative_path = source.relative_to(root)
                except ValueError:
                    relative_path = Path(source.name)
                candidates.append(
                    {
                        "field": field,
                        "path": source,
                        "relative_path": relative_path,
                    }
                )
        return candidates

    def _is_supported_workspace_baseline_content_file(
        self,
        record: ManagedObjectRecord,
        field: str,
        path: Path,
    ) -> bool:
        if field == "config_dir":
            return True
        if field == "data_dir" and record.type_name.lower() in {"sqlite", "database"}:
            return path.suffix.lower() in {".db", ".sqlite", ".sqlite3"}
        return False

    def _restore_workspace_baseline_content_references(
        self,
        record: WorkspaceBaselineRecord,
    ) -> dict[str, Any]:
        metadata = record.metadata if isinstance(record.metadata, dict) else {}
        snapshots = (
            metadata.get("content_reference_snapshots", [])
            if isinstance(metadata.get("content_reference_snapshots"), list)
            else []
        )
        restored_contents: list[dict[str, Any]] = []
        overwritten_contents: list[dict[str, Any]] = []
        unchanged_contents: list[dict[str, Any]] = []
        skipped_contents: list[dict[str, Any]] = []
        baseline_root = self.storage.baselines_dir.resolve()
        workspace_root = self.root_path.resolve()
        for item in snapshots:
            if not isinstance(item, dict):
                continue
            raw_stored_path = item.get("stored_path")
            raw_target_path = item.get("path")
            if not isinstance(raw_stored_path, str) or not isinstance(
                raw_target_path,
                str,
            ):
                continue
            source = (self.storage.baselines_dir / raw_stored_path).resolve()
            target = Path(raw_target_path).expanduser().resolve()
            object_name = str(item.get("object_name", ""))
            field = str(item.get("field", ""))
            if not source.is_relative_to(baseline_root):
                skipped_contents.append(
                    {
                        "object_name": object_name,
                        "field": field,
                        "path": raw_stored_path,
                        "reason": "invalid_baseline_content_path",
                    }
                )
                continue
            if not target.is_relative_to(workspace_root):
                skipped_contents.append(
                    {
                        "object_name": object_name,
                        "field": field,
                        "path": str(target),
                        "reason": "target_outside_workspace_not_supported",
                    }
                )
                continue
            if not source.exists() or not source.is_file():
                skipped_contents.append(
                    {
                        "object_name": object_name,
                        "field": field,
                        "path": str(target),
                        "reason": "baseline_content_file_not_found",
                    }
                )
                continue
            if target.exists() and target.is_dir():
                skipped_contents.append(
                    {
                        "object_name": object_name,
                        "field": field,
                        "path": str(target),
                        "reason": "target_path_is_directory",
                    }
                )
                continue
            try:
                target_exists = target.exists()
                target_sha256 = self._sha256_file(target) if target_exists else None
                source_sha256 = self._sha256_file(source)
                result_entry = {
                    "object_name": object_name,
                    "field": field,
                    "path": str(target),
                    "size_bytes": item.get("size_bytes"),
                    "sha256": item.get("sha256", source_sha256),
                }
                if target_sha256 == source_sha256:
                    unchanged_contents.append(
                        {
                            **result_entry,
                            "action": "already_at_baseline",
                        }
                    )
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                if target_exists:
                    overwritten_contents.append(
                        {
                            **result_entry,
                            "action": "overwritten_to_baseline",
                            "previous_sha256": target_sha256,
                        }
                    )
                else:
                    restored_contents.append(
                        {
                            **result_entry,
                            "action": "created_from_baseline",
                        }
                    )
            except OSError as exc:
                skipped_contents.append(
                    {
                        "object_name": object_name,
                        "field": field,
                        "path": str(target),
                        "reason": str(exc),
                    }
                )
        return {
            "scope": "workspace_content_reference_restore",
            "restored_contents": restored_contents,
            "overwritten_contents": overwritten_contents,
            "unchanged_contents": unchanged_contents,
            "skipped_contents": skipped_contents,
            "limitations": [
                "only small explicitly supported content files are restored",
                "full database image restoration is not included in this stage",
                "container/system rollback is not included in this stage",
            ],
        }

    def _build_workspace_baseline_content_skip(
        self,
        record: ManagedObjectRecord,
        field: str,
        path: Path,
        reason: str,
    ) -> dict[str, Any]:
        return {
            "object_name": record.name,
            "type_name": record.type_name,
            "field": field,
            "path": str(path),
            "reason": reason,
        }

    def _safe_workspace_baseline_path_segment(self, value: str) -> str:
        safe_value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
        return safe_value or "object"

    def _sha256_file(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file_obj:
            for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _build_workspace_recovery_post_checks(
        self,
        *,
        problem_type: str,
        problem_id: str,
        affected_objects: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        checks: list[dict[str, Any]] = []
        if affected_objects:
            checks.append(
                {
                    "priority": "high",
                    "action": "verify_recovered_object_state",
                    "objects": [
                        item["object_name"]
                        for item in affected_objects
                        if isinstance(item.get("object_name"), str)
                    ],
                    "reason": "confirm the affected objects reached the expected baseline state before deeper validation",
                }
            )
        follow_up_action = {
            "api_response": "replay_problem",
            "data_state": "rerun_problem_recover",
            "service_runtime": "rerun_service_validation",
            "crash_dump": "inspect_preserved_dump_and_rerun_runtime_validation",
        }.get(problem_type, "inspect_problem_state")
        checks.append(
            {
                "priority": "medium",
                "action": follow_up_action,
                "problem_id": problem_id,
                "reason": "revalidate the original problem path after the minimal recovery actions are applied",
            }
        )
        return checks

    def _build_api_recovery_plan(
        self, record: ProblemRecord, assets: ProblemAssetRecord
    ) -> dict[str, Any]:
        recovery = assets.recovery if isinstance(assets.recovery, dict) else {}
        replay = recovery.get("replay", {}) if isinstance(recovery, dict) else {}
        request = replay if isinstance(replay, dict) else {}
        return {
            "problem_id": record.problem_id,
            "problem_type": record.problem_type,
            "summary": record.summary,
            "supported": bool(recovery.get("supported", False)),
            "mode": recovery.get("mode", "request_replay"),
            "steps": [
                "Inspect the preserved request payload and target endpoint.",
                "Replay the same request against the current target service.",
                "Compare the replay response with the preserved failure context.",
            ],
            "request": request,
            "hints": recovery,
        }

    def _build_data_recovery_plan(
        self, record: ProblemRecord, assets: ProblemAssetRecord
    ) -> dict[str, Any]:
        recovery = assets.recovery if isinstance(assets.recovery, dict) else {}
        details = assets.details if isinstance(assets.details, dict) else {}
        data_source = details.get("data_source", {})
        operations = details.get("operations", [])
        recommended_queries = recovery.get("recommended_queries", [])
        suggested_repairs = recovery.get("suggested_repairs", [])
        next_actions = recovery.get("next_actions", [])
        limitations = recovery.get("limitations", [])
        failure_kind = recovery.get("failure_kind", details.get("failure_kind"))
        origin_hints = recovery.get("origin_hints", details.get("origin_hints", {}))
        boundary = recovery.get("boundary", {})
        data_state_artifacts = details.get("data_state_artifacts")
        state_snapshot = self._summarize_data_state_artifacts(data_state_artifacts)
        return {
            "problem_id": record.problem_id,
            "problem_type": record.problem_type,
            "summary": record.summary,
            "supported": bool(recovery.get("supported", False)),
            "mode": recovery.get("mode", "minimal_state_hints"),
            "goal": "identify the minimal data/state correction needed before rerunning the preserved query",
            "failure_kind": failure_kind,
            "steps": [
                "Verify the target database or data source is reachable.",
                "Recreate or inspect the minimal precondition data before rerunning the query.",
                "Run the preserved query and compare actual vs expected results.",
            ],
            "data_source": data_source if isinstance(data_source, dict) else {},
            "operations": operations if isinstance(operations, list) else [],
            "expected_result": details.get("expected_result"),
            "actual_result": details.get("actual_result"),
            "state_hints": recovery.get("state_hints", details.get("state_hints", {})),
            "origin_hints": origin_hints if isinstance(origin_hints, dict) else {},
            "boundary": boundary if isinstance(boundary, dict) else {},
            "recommended_queries": (
                recommended_queries if isinstance(recommended_queries, list) else []
            ),
            "suggested_repairs": (
                suggested_repairs if isinstance(suggested_repairs, list) else []
            ),
            "next_actions": next_actions if isinstance(next_actions, list) else [],
            "limitations": limitations if isinstance(limitations, list) else [],
            "state_snapshot": state_snapshot,
            "hints": recovery,
        }

    def _analyze_data_state_problem(
        self,
        *,
        expected_result: Any,
        actual_result: Any,
        query: str,
    ) -> dict[str, Any]:
        expected_rows = expected_result if isinstance(expected_result, list) else None
        actual_rows = actual_result if isinstance(actual_result, list) else None
        failure_kind = "shape_mismatch"
        state_hints: dict[str, Any] = {
            "expected_type": self._problem_value_type_name(expected_result),
            "actual_type": self._problem_value_type_name(actual_result),
        }

        if expected_rows is not None and actual_rows is not None:
            state_hints["expected_row_count"] = len(expected_rows)
            state_hints["actual_row_count"] = len(actual_rows)
            if expected_rows and not actual_rows:
                failure_kind = "missing_rows"
                state_hints["missing_row_count"] = len(expected_rows)
            elif not expected_rows and actual_rows:
                failure_kind = "unexpected_rows"
                state_hints["unexpected_row_count"] = len(actual_rows)
            elif len(expected_rows) != len(actual_rows):
                if len(actual_rows) < len(expected_rows):
                    failure_kind = "missing_rows"
                    state_hints["missing_row_count"] = len(expected_rows) - len(
                        actual_rows
                    )
                else:
                    failure_kind = "unexpected_rows"
                    state_hints["unexpected_row_count"] = len(actual_rows) - len(
                        expected_rows
                    )
            elif not self._compare_problem_values(expected_rows, actual_rows):
                failure_kind = "value_mismatch"
                state_hints["mismatched_fields"] = (
                    self._collect_data_state_mismatch_fields(expected_rows, actual_rows)
                )
            else:
                failure_kind = "unknown"
        elif self._problem_value_type_name(
            expected_result
        ) != self._problem_value_type_name(actual_result):
            failure_kind = "shape_mismatch"
        elif not self._compare_problem_values(expected_result, actual_result):
            failure_kind = "value_mismatch"

        recommended_queries = self._build_data_state_recommended_queries(query)
        suggested_repairs = self._build_data_state_suggested_repairs(
            failure_kind=failure_kind,
            state_hints=state_hints,
        )
        next_actions = self._build_data_state_next_actions(
            failure_kind=failure_kind,
            query=query,
        )
        limitations = [
            "current recovery output is a plan only and does not execute data changes automatically",
            "current data_state recovery does not reconstruct full historical database state",
        ]
        return {
            "failure_kind": failure_kind,
            "state_hints": state_hints,
            "recommended_queries": recommended_queries,
            "suggested_repairs": suggested_repairs,
            "next_actions": next_actions,
            "limitations": limitations,
        }

    def _build_data_state_origin_hints(
        self,
        *,
        execution_id: str,
        case_id: str,
        failure_kind: str,
        query: str,
    ) -> dict[str, Any]:
        dependency_hints = self._build_problem_dependency_hints(
            execution_id=execution_id,
            case_id=case_id,
        )
        classification = {
            "missing_rows": "missing_seed_data",
            "unexpected_rows": "unexpected_residual_data",
            "value_mismatch": "stale_field_values",
            "shape_mismatch": "query_scope_mismatch",
        }.get(failure_kind, "unknown_state_origin")
        query_context = self._classify_data_state_query_context(query)
        signal_strength = dependency_hints.get("signal_strength", "none")
        if failure_kind in {"missing_rows", "unexpected_rows", "value_mismatch"}:
            signal_strength = (
                signal_strength if signal_strength != "none" else "direct_result_only"
            )
        return {
            **dependency_hints,
            "classification": classification,
            "query_context": query_context,
            "signal_strength": signal_strength,
        }

    def _classify_data_state_query_context(self, query: str) -> str:
        normalized = query.strip().lower()
        if not normalized:
            return "unknown"
        if "count(" in normalized:
            return "count_query"
        if " where " in normalized and "status" in normalized:
            return "status_filtered_query"
        if " where " in normalized:
            return "single_or_filtered_query"
        if " limit " in normalized:
            return "bounded_list_query"
        if normalized.startswith("select"):
            return "list_query"
        return "unknown"

    def _build_data_state_recovery_boundary(
        self,
        *,
        failure_kind: str,
        origin_hints: dict[str, Any],
    ) -> dict[str, Any]:
        signal_strength = str(origin_hints.get("signal_strength", "none"))
        candidate_case_ids = origin_hints.get("candidate_case_ids", [])
        has_predecessors = isinstance(candidate_case_ids, list) and bool(
            candidate_case_ids
        )
        confidence = {
            "value_mismatch": "high_for_direct_result_mismatch",
            "missing_rows": "medium_for_missing_rows",
            "unexpected_rows": "medium_for_unexpected_rows",
            "shape_mismatch": "low_when_context_is_sparse",
        }.get(failure_kind, "low_when_context_is_sparse")
        if has_predecessors:
            confidence = "reduced_by_recent_execution_context"
        assessment = "query_level_plan"
        reason = "current recovery plan summarizes query-level evidence only and does not reconstruct historical database state"
        if has_predecessors:
            assessment = "possible_precondition_or_sequence_dependency"
            reason = "recent executions may have changed the data state before this preserved failure, so the current recovery plan should be treated as a query-level hint"
        recommended_actions = origin_hints.get("recommended_actions", [])
        if not isinstance(recommended_actions, list):
            recommended_actions = []
        return {
            "scope": "query_level_plan",
            "confidence": confidence,
            "assessment": assessment,
            "signal_strength": signal_strength,
            "reason": reason,
            "needs_historical_state": has_predecessors,
            "does_not_cover": [
                "historical_database_state_reconstruction",
                "cross_table_dependency_inference",
                "automatic_data_repair_execution",
            ],
            "recommended_actions": recommended_actions,
        }

    def _collect_data_state_mismatch_fields(
        self, expected_rows: list[Any], actual_rows: list[Any]
    ) -> list[str]:
        if not expected_rows or not actual_rows:
            return []
        expected_first = expected_rows[0]
        actual_first = actual_rows[0]
        if isinstance(expected_first, dict) and isinstance(actual_first, dict):
            keys = sorted(set(expected_first.keys()) | set(actual_first.keys()))
            return [
                str(key)
                for key in keys
                if not self._compare_problem_values(
                    expected_first.get(key), actual_first.get(key)
                )
            ]
        return []

    def _build_data_state_recommended_queries(self, query: str) -> list[dict[str, Any]]:
        queries: list[dict[str, Any]] = []
        if query:
            queries.append(
                {
                    "purpose": "rerun_preserved_query",
                    "query": query,
                }
            )
        queries.append(
            {
                "purpose": "inspect_row_count",
                "query": "Run a lightweight count query against the same target table or view to confirm whether rows are missing or unexpectedly added.",
            }
        )
        return queries

    def _build_data_state_suggested_repairs(
        self,
        *,
        failure_kind: str,
        state_hints: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if failure_kind == "missing_rows":
            return [
                {
                    "action": "insert_minimal_required_rows",
                    "reason": "expected rows were not present when the preserved query ran",
                    "missing_row_count": state_hints.get("missing_row_count"),
                }
            ]
        if failure_kind == "unexpected_rows":
            return [
                {
                    "action": "remove_or_filter_unexpected_rows",
                    "reason": "the query returned more rows than expected",
                    "unexpected_row_count": state_hints.get("unexpected_row_count"),
                }
            ]
        if failure_kind == "value_mismatch":
            return [
                {
                    "action": "align_key_field_values",
                    "reason": "the returned rows exist but key values differ from the expected result",
                    "fields": state_hints.get("mismatched_fields", []),
                }
            ]
        return [
            {
                "action": "inspect_result_shape",
                "reason": "the actual result shape differs from the expected result and needs manual inspection",
            }
        ]

    def _build_data_state_next_actions(
        self, *, failure_kind: str, query: str
    ) -> list[dict[str, Any]]:
        actions = [
            {
                "priority": "high",
                "action": "inspect_data_source_connectivity",
                "reason": "confirm the target database or bound data source is reachable before investigating result differences",
            }
        ]
        if query:
            actions.append(
                {
                    "priority": "high",
                    "action": "rerun_preserved_query_manually",
                    "query": query,
                    "reason": "recheck the preserved query output before applying any data repair",
                }
            )
        repair_action = {
            "missing_rows": "restore_missing_rows",
            "unexpected_rows": "clean_unexpected_rows",
            "value_mismatch": "correct_mismatched_values",
        }.get(failure_kind, "inspect_result_shape")
        actions.append(
            {
                "priority": "medium",
                "action": repair_action,
                "reason": "apply the minimal state correction suggested by the preserved failure analysis",
            }
        )
        return actions

    def _build_environment_dependency_recovery_plan(
        self, record: ProblemRecord, assets: ProblemAssetRecord
    ) -> dict[str, Any]:
        recovery = assets.recovery if isinstance(assets.recovery, dict) else {}
        details = assets.details if isinstance(assets.details, dict) else {}
        return {
            "problem_id": record.problem_id,
            "problem_type": record.problem_type,
            "summary": record.summary,
            "supported": bool(recovery.get("supported", False)),
            "mode": recovery.get("mode", "minimal_environment_recovery"),
            "steps": [
                "Inspect the preserved environment and dependency summary.",
                "Fix the missing or invalid object/environment prerequisite.",
                "Retry the minimal environment preparation step before rerunning cases.",
            ],
            "environment": details.get("environment"),
            "objects": details.get("objects"),
            "phase": details.get("phase"),
            "message": details.get("message"),
            "missing_libraries": details.get("missing_libraries", []),
            "dependency_requirements": details.get("dependency_requirements", {}),
            "hints": recovery,
        }

    def _build_service_runtime_recovery_plan(
        self, record: ProblemRecord, assets: ProblemAssetRecord
    ) -> dict[str, Any]:
        recovery = assets.recovery if isinstance(assets.recovery, dict) else {}
        details = assets.details if isinstance(assets.details, dict) else {}
        service = details.get("service", {})
        runtime_result = details.get("runtime_result", {})
        recommended_checks = recovery.get("recommended_checks", [])
        suggested_repairs = recovery.get("suggested_repairs", [])
        next_actions = recovery.get("next_actions", [])
        limitations = recovery.get("limitations", [])
        runtime_target = recovery.get("runtime_target", {})
        runtime_hints = recovery.get("runtime_hints", details.get("runtime_hints", {}))
        boundary = recovery.get("boundary", {})
        return {
            "problem_id": record.problem_id,
            "problem_type": record.problem_type,
            "summary": record.summary,
            "supported": bool(recovery.get("supported", False)),
            "mode": recovery.get("mode", "runtime_level_plan"),
            "goal": "identify the minimal runtime correction needed before rerunning the preserved service check",
            "failure_kind": recovery.get(
                "failure_kind", details.get("failure_kind", "healthcheck_failed")
            ),
            "steps": [
                "Inspect the preserved service endpoint and runtime failure summary.",
                "Verify the target service status, endpoint reachability and recent runtime logs.",
                "Apply the minimal runtime correction before rerunning the preserved service validation.",
            ],
            "runtime_target": runtime_target
            if isinstance(runtime_target, dict)
            else {},
            "service": service if isinstance(service, dict) else {},
            "runtime_result": runtime_result
            if isinstance(runtime_result, dict)
            else {},
            "runtime_hints": runtime_hints if isinstance(runtime_hints, dict) else {},
            "boundary": boundary if isinstance(boundary, dict) else {},
            "recommended_checks": (
                recommended_checks if isinstance(recommended_checks, list) else []
            ),
            "suggested_repairs": (
                suggested_repairs if isinstance(suggested_repairs, list) else []
            ),
            "next_actions": next_actions if isinstance(next_actions, list) else [],
            "limitations": limitations if isinstance(limitations, list) else [],
            "hints": recovery,
        }

    def _build_crash_dump_recovery_plan(
        self, record: ProblemRecord, assets: ProblemAssetRecord
    ) -> dict[str, Any]:
        recovery = assets.recovery if isinstance(assets.recovery, dict) else {}
        details = assets.details if isinstance(assets.details, dict) else {}
        crash_target = recovery.get("crash_target", details.get("crash_target", {}))
        dump_refs = recovery.get("dump_refs", details.get("dump_refs", []))
        boundary = recovery.get("boundary", {})
        recommended_checks = recovery.get("recommended_checks", [])
        next_actions = recovery.get("next_actions", [])
        limitations = recovery.get("limitations", [])
        return {
            "problem_id": record.problem_id,
            "problem_type": record.problem_type,
            "summary": record.summary,
            "supported": bool(recovery.get("supported", False)),
            "mode": recovery.get("mode", "crash_dump_investigation"),
            "goal": "preserve and inspect the minimal crash assets before deeper dump analysis",
            "crash_target": crash_target if isinstance(crash_target, dict) else {},
            "dump_refs": dump_refs if isinstance(dump_refs, list) else [],
            "boundary": boundary if isinstance(boundary, dict) else {},
            "recommended_checks": (
                recommended_checks if isinstance(recommended_checks, list) else []
            ),
            "next_actions": next_actions if isinstance(next_actions, list) else [],
            "limitations": limitations if isinstance(limitations, list) else [],
            "hints": recovery,
        }

    def _record_environment_dependency_problem(
        self,
        *,
        problem_type: str,
        summary: str,
        details: dict[str, Any],
        recovery: dict[str, Any],
        object_refs: list[str] | None = None,
    ) -> str:
        env_context = self._environment_problem_context()
        problem_id = f"problem_{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()
        refs = object_refs or []
        preservation = self._build_preservation_summary(
            {
                "environment_snapshot": (
                    bool(env_context["environment"]),
                    "environment snapshot is not available",
                ),
                "object_snapshot": (
                    bool(env_context["objects"]),
                    "related object snapshot is not available",
                ),
                "recovery_hints": (
                    bool(recovery),
                    "recovery hints were not generated",
                ),
                "log_index": (
                    bool(env_context["log_refs"].get("workspace_logs_dir")),
                    "log index is not available",
                ),
            }
        )
        problem_record = self._new_problem_record(
            problem_id=problem_id,
            problem_type=problem_type,
            summary=summary,
            preservation=preservation,
            execution_id="",
            case_id="",
            environment_id=env_context["environment_id"],
            object_refs=refs,
            artifact_refs={},
            log_refs=env_context["log_refs"],
            created_at=now,
            updated_at=now,
            metadata={"source": "environment_dependency"},
        )
        problem_assets = self._new_problem_assets(
            problem_id=problem_id,
            problem_type=problem_type,
            summary=summary,
            preservation=preservation,
            execution_id="",
            case_id="",
            environment_id=env_context["environment_id"],
            object_refs=refs,
            artifact_refs={},
            log_refs=env_context["log_refs"],
            recovery=recovery,
            details={
                **details,
                "environment": env_context["environment"],
                "objects": env_context["objects"],
                "preservation": preservation,
            },
            created_at=now,
            updated_at=now,
            metadata={"source": "environment_dependency"},
        )
        self._save_problem_bundle(problem_record, problem_assets)
        return problem_id

    def _record_problem_recovery_action(
        self,
        record: ProblemRecord,
        assets: ProblemAssetRecord,
        *,
        action_type: str,
        success: bool,
        status: str,
        result: dict[str, Any],
    ) -> ProblemRecoveryRecord:
        now = datetime.now().isoformat()
        raw_mode = result.get("mode", "unknown")
        mode = raw_mode if isinstance(raw_mode, str) else "unknown"
        action_id = f"recovery_{uuid.uuid4().hex[:12]}"
        recovery_record = ProblemRecoveryRecord(
            action_id=action_id,
            problem_id=record.problem_id,
            problem_type=record.problem_type,
            action_type=action_type,
            mode=mode,
            success=success,
            status=status,
            execution_id=record.execution_id,
            case_id=record.case_id,
            environment_id=record.environment_id,
            created_at=now,
            updated_at=now,
            metadata={
                "result": result,
                "latest_problem_status": record.status,
            },
        )
        self.storage.save_problem_recovery_history(recovery_record)
        self.storage.save_problem_recovery(recovery_record)

        latest_recovery = {
            "action_id": action_id,
            "action_type": action_type,
            "status": status,
            "mode": mode,
            "success": success,
            "created_at": now,
            "result_summary": self._build_problem_latest_recovery_summary(
                action_type=action_type,
                result=result,
            ),
        }
        record.latest_action = f"{action_type}:{status}"
        record.updated_at = now
        record.metadata["latest_recovery"] = latest_recovery
        assets.metadata["latest_recovery"] = latest_recovery
        assets.updated_at = now

        self._save_problem_bundle(record, assets)
        return recovery_record

    def _build_problem_latest_recovery_summary(
        self, *, action_type: str, result: dict[str, Any]
    ) -> dict[str, Any]:
        if action_type == "replay":
            comparison = result.get("comparison")
            return {
                "reproduced": result.get("reproduced"),
                "comparison": comparison if isinstance(comparison, dict) else None,
            }
        if action_type == "recover":
            return {
                "mode": result.get("mode"),
                "problem_type": result.get("problem_type"),
                "workspace_recovery": result.get("workspace_recovery"),
            }
        return {}

    def _new_problem_record(
        self,
        *,
        problem_id: str,
        problem_type: str,
        summary: str,
        preservation: dict[str, Any],
        execution_id: str,
        case_id: str,
        environment_id: str,
        object_refs: list[str],
        artifact_refs: dict[str, Any],
        log_refs: dict[str, Any],
        created_at: str,
        updated_at: str,
        metadata: dict[str, Any] | None = None,
    ) -> ProblemRecord:
        record_metadata = dict(metadata or {})
        record_metadata["preservation"] = preservation
        record_metadata["capabilities"] = self._problem_capabilities(
            problem_type,
            recovery=None,
        )
        return ProblemRecord(
            problem_id=problem_id,
            problem_type=problem_type,
            summary=summary,
            status=PROBLEM_STATUS_OPEN,
            preservation_status=self._problem_preservation_status(preservation),
            execution_id=execution_id,
            case_id=case_id,
            environment_id=environment_id,
            object_refs=list(object_refs),
            artifact_refs=dict(artifact_refs),
            log_refs=dict(log_refs),
            latest_action=PROBLEM_ACTION_PRESERVED,
            created_at=created_at,
            updated_at=updated_at,
            metadata=record_metadata,
        )

    def _new_problem_assets(
        self,
        *,
        problem_id: str,
        problem_type: str,
        summary: str,
        preservation: dict[str, Any],
        execution_id: str,
        case_id: str,
        environment_id: str,
        object_refs: list[str],
        artifact_refs: dict[str, Any],
        log_refs: dict[str, Any],
        recovery: dict[str, Any],
        details: dict[str, Any],
        created_at: str,
        updated_at: str,
        metadata: dict[str, Any] | None = None,
    ) -> ProblemAssetRecord:
        asset_metadata = dict(metadata or {})
        asset_metadata["preservation"] = preservation
        asset_metadata["capabilities"] = self._problem_capabilities(
            problem_type,
            recovery=recovery,
        )
        runtime_backend = self._build_problem_runtime_backend_context(object_refs)
        if runtime_backend:
            asset_metadata["runtime_backend"] = runtime_backend
        return ProblemAssetRecord(
            problem_id=problem_id,
            problem_type=problem_type,
            summary=summary,
            status=PROBLEM_STATUS_OPEN,
            preservation_status=self._problem_preservation_status(preservation),
            execution_id=execution_id,
            case_id=case_id,
            environment_id=environment_id,
            object_refs=list(object_refs),
            artifact_refs=dict(artifact_refs),
            log_refs=dict(log_refs),
            recovery=dict(recovery),
            details=dict(details),
            created_at=created_at,
            updated_at=updated_at,
            metadata=asset_metadata,
        )

    def _problem_preservation_status(self, preservation: dict[str, Any]) -> str:
        status = preservation.get("status", PROBLEM_PRESERVATION_SUCCESS)
        if status in {
            PROBLEM_PRESERVATION_SUCCESS,
            PROBLEM_PRESERVATION_PARTIAL,
            PROBLEM_PRESERVATION_FAILED,
        }:
            return cast(str, status)
        return PROBLEM_PRESERVATION_SUCCESS

    def _save_problem_bundle(
        self,
        problem_record: ProblemRecord,
        problem_assets: ProblemAssetRecord,
    ) -> None:
        capabilities = self._problem_capabilities(
            problem_record.problem_type,
            recovery=problem_assets.recovery,
        )
        problem_record.metadata["capabilities"] = capabilities
        problem_assets.metadata["capabilities"] = capabilities
        self.storage.save_problem_record(problem_record)
        self.storage.save_problem_assets(problem_assets)

    def _problem_capabilities(
        self,
        problem_type: str,
        *,
        recovery: dict[str, Any] | None,
    ) -> dict[str, Any]:
        replay_supported = self._supports_problem_replay_type(problem_type) and bool(
            isinstance(recovery, dict)
            and isinstance(recovery.get("replay"), dict)
            and recovery["replay"].get("url")
        )
        recover_supported = self._supports_problem_recovery_type(problem_type)
        raw_mode = recovery.get("mode") if isinstance(recovery, dict) else None
        mode = raw_mode if isinstance(raw_mode, str) and raw_mode else None
        return {
            "can_replay": replay_supported,
            "can_recover": recover_supported,
            "replay_mode": mode if replay_supported else None,
            "recover_mode": mode if recover_supported else None,
        }

    def _supports_problem_replay(self, assets: ProblemAssetRecord) -> bool:
        if not self._supports_problem_replay_type(assets.problem_type):
            return False
        replay = (
            assets.recovery.get("replay") if isinstance(assets.recovery, dict) else {}
        )
        return isinstance(replay, dict) and bool(replay.get("url"))

    def _supports_problem_recovery(self, assets: ProblemAssetRecord) -> bool:
        return self._supports_problem_recovery_type(assets.problem_type)

    def _supports_problem_replay_type(self, problem_type: str) -> bool:
        return problem_type == "api_response"

    def _supports_problem_recovery_type(self, problem_type: str) -> bool:
        return problem_type in {
            "api_response",
            "data_state",
            "environment_init",
            "dependency_object",
            "dependency_configuration",
            "service_runtime",
            "crash_dump",
        }

    def _build_preservation_summary(
        self,
        checks: dict[str, tuple[bool, str]],
    ) -> dict[str, Any]:
        required_assets = list(checks.keys())
        available_assets: list[str] = []
        missing_assets: list[str] = []
        missing_reasons: dict[str, str] = {}

        for asset_name, (is_available, missing_reason) in checks.items():
            if is_available:
                available_assets.append(asset_name)
            else:
                missing_assets.append(asset_name)
                missing_reasons[asset_name] = missing_reason

        status = "success"
        if missing_assets:
            status = "partial" if available_assets else "missing"

        return {
            "status": status,
            "required_assets": required_assets,
            "available_assets": available_assets,
            "missing_assets": missing_assets,
            "missing_reasons": missing_reasons,
        }

    def _classify_object_install_problem(
        self,
        normalized_type: str,
        params: dict[str, Any],
        result: str,
    ) -> str:
        result_lower = result.lower()
        if not params:
            return "dependency_configuration"
        if any(
            marker in result_lower
            for marker in {
                "requires parameters",
                "unsupported",
                "connection test failed",
                "missing",
                "invalid",
            }
        ):
            return "dependency_configuration"
        if normalized_type == "database" and not any(
            key in params for key in {"db_type", "driver"}
        ):
            return "dependency_configuration"
        return "dependency_object"

    def _classify_object_state_problem(
        self,
        record: ManagedObjectRecord,
        action: str,
        result: str,
    ) -> str:
        result_lower = result.lower()
        if action == "start" and self._extract_missing_shared_libraries(result):
            return "dependency_configuration"
        config = record.config if isinstance(record.config, dict) else {}
        if (
            action == "start"
            and str(config.get("db_type", "")).lower() == "mysql"
            and (
                ("missing" in result_lower and "library" in result_lower)
                or "runtime backend" in result_lower
                or "does not permit binding" in result_lower
                or "operation not permitted" in result_lower
            )
        ):
            return "dependency_configuration"
        return "dependency_object"

    def _extract_missing_shared_libraries(self, result: str) -> list[str]:
        marker = "missing required shared libraries:"
        result_lower = result.lower()
        if marker not in result_lower:
            return []
        missing_text = result[result_lower.index(marker) + len(marker) :].strip()
        return [item.strip() for item in missing_text.split(",") if item.strip()]

    def _environment_problem_context(self) -> dict[str, Any]:
        environment_record = self.storage.load_environment()
        objects = self.storage.load_objects()
        environment = (
            environment_record.to_dict()
            if environment_record is not None
            else {
                "root_path": str(self.root_path),
                "status": "uninitialized",
                "metadata": {},
            }
        )
        environment_id = ""
        metadata = environment.get("metadata", {})
        if isinstance(metadata, dict):
            isolation = metadata.get("isolation", {})
            if isinstance(isolation, dict):
                env_id = isolation.get("env_id")
                if isinstance(env_id, str):
                    environment_id = env_id
        logs_dir = self.root_path / "logs"
        return {
            "environment": environment,
            "environment_id": environment_id,
            "objects": [record.to_dict() for record in objects.values()],
            "log_refs": {
                "workspace_logs_dir": str(logs_dir.relative_to(self.root_path))
                if logs_dir.exists()
                else "logs"
            },
        }

    def _existing_tool_created_at(self, name: str) -> str:
        record = self.storage.get_tool(name)
        if record is None:
            return datetime.now().isoformat()
        return record.created_at

    def _operation_result(
        self,
        *,
        success: bool,
        status: str,
        message: str,
        data: Any | None = None,
        error: Any | None = None,
        error_code: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        payload = {
            "success": success,
            "status": status,
            "message": message,
            "error": error,
            "error_code": error_code,
            "workspace": str(self.root_path),
        }
        if data is not None:
            payload["data"] = data
        payload.update(extra)
        return payload

    def _not_found_result(self, entity: str, name: str) -> dict[str, Any]:
        return self._operation_result(
            success=False,
            status="not_found",
            message=f"{entity.capitalize()} '{name}' does not exist",
            error=f"{entity}_not_found",
            error_code=f"{entity}_not_found",
        )

    def _ensure_isolation_environment(
        self, existing: EnvironmentRecord | None
    ) -> dict[str, Any]:
        manager = self._get_isolation_manager()
        isolation = self._resolve_isolation_settings(existing)
        isolation_level = isolation["isolation_level"]
        env_id = isolation["env_id"]
        env_config = isolation["config"]

        if env_id:
            env, recovery_strategy = self._attach_isolation_environment(
                env_id,
                isolation_level,
                env_config,
            )
            return self._isolation_metadata(
                env,
                isolation_level,
                attached=True,
                recovery_strategy=recovery_strategy,
            )

        env = manager.create_environment(
            self.root_path,
            isolation_level=isolation_level,
            env_config=env_config or None,
        )
        env.activate()
        return self._isolation_metadata(
            env,
            isolation_level,
            attached=False,
            recovery_strategy="created_new",
        )

    def _attach_isolation_environment(
        self,
        env_id: str,
        isolation_level: str,
        env_config: dict[str, Any] | None = None,
    ) -> tuple[Any, str]:
        manager = self._get_isolation_manager()
        attached = manager.get_environment(env_id)
        if attached is not None:
            return attached, "attached_active"

        engine = manager.engines.get(isolation_level)
        if engine is None:
            engine_config = self.config.get(isolation_level, {})
            if not isinstance(engine_config, dict):
                engine_config = {}
            engine = manager.registry.create_engine(
                isolation_level,
                cast(dict[str, Any], engine_config),
            )
            if engine is not None:
                manager.engines[isolation_level] = engine
        if engine is None:
            raise ValueError(f"Unsupported isolation level: {isolation_level}")

        isolation_config = (env_config or {}).copy()
        engine_defaults = self.config.get(isolation_level, {})
        if isinstance(engine_defaults, dict):
            isolation_config.update(cast(dict[str, Any], engine_defaults))
        env = engine.create_isolation(self.root_path, env_id, isolation_config)
        manager.active_environments[env_id] = env
        if not hasattr(engine, "created_environments"):
            engine.created_environments = {}
        engine.created_environments[env_id] = env
        env.activate()
        return env, "reattached_recreated"

    def _cleanup_isolation_environment(
        self,
        record: EnvironmentRecord,
    ) -> dict[str, Any]:
        isolation = self._resolve_isolation_settings(record)
        env_id = isolation["env_id"]
        isolation_level = isolation["isolation_level"]
        env_config = isolation["config"]
        if not env_id:
            return {
                "success": False,
                "skipped": True,
                "messages": [],
                "strategy": "no_isolation_metadata",
            }

        manager = self._get_isolation_manager()
        messages: list[str] = []
        cleanup_strategy = "reattach_and_cleanup"
        try:
            env, attach_strategy = self._attach_isolation_environment(
                env_id,
                isolation_level,
                env_config,
            )
            cleanup_strategy = f"{attach_strategy}_cleanup"
            deactivated = env.deactivate()
            messages.append(
                f"Isolation environment '{env_id}' deactivated"
                if deactivated
                else f"Isolation environment '{env_id}' deactivation skipped"
            )
            cleaned = env.cleanup(force=False)
            forced = False
            if not cleaned:
                cleaned = env.cleanup(force=True)
                forced = cleaned
                if forced:
                    messages.append(
                        f"Isolation environment '{env_id}' cleanup completed with force"
                    )
            if env_id in manager.active_environments:
                del manager.active_environments[env_id]
            engine = manager.engines.get(isolation_level)
            if engine is not None and env_id in engine.created_environments:
                del engine.created_environments[env_id]
            if not forced:
                messages.append(
                    f"Isolation environment '{env_id}' cleanup completed"
                    if cleaned
                    else f"Isolation environment '{env_id}' cleanup reported failure"
                )
            return {
                "success": cleaned,
                "skipped": False,
                "env_id": env_id,
                "isolation_level": isolation_level,
                "forced": forced,
                "strategy": cleanup_strategy,
                "messages": messages,
            }
        except Exception as exc:
            messages.append(f"Isolation environment '{env_id}' cleanup failed: {exc}")
            return {
                "success": False,
                "skipped": False,
                "env_id": env_id,
                "isolation_level": isolation_level,
                "strategy": cleanup_strategy,
                "messages": messages,
                "error": str(exc),
            }

    def _resolve_isolation_settings(
        self,
        record: EnvironmentRecord | None,
    ) -> dict[str, Any]:
        isolation = record.metadata.get("isolation", {}) if record else {}
        isolation_level = isolation.get("isolation_level")
        if not isinstance(isolation_level, str):
            fallback_isolation_level = (
                record.isolation_level
                if record
                else self.config.get("default_isolation_level", "basic")
            )
            isolation_level = (
                fallback_isolation_level
                if isinstance(fallback_isolation_level, str)
                else "basic"
            )
        isolation_config = isolation.get("config", {})
        if not isinstance(isolation_config, dict):
            isolation_config = {}
        return {
            "env_id": isolation.get("env_id"),
            "isolation_level": isolation_level,
            "config": isolation_config,
        }

    def _isolation_metadata(
        self,
        env: Any,
        isolation_level: str,
        *,
        attached: bool,
        recovery_strategy: str,
    ) -> dict[str, Any]:
        status = env.get_status()
        validation = self._get_isolation_validation(env)
        return {
            "env_id": env.env_id,
            "isolation_level": isolation_level,
            "attached": attached,
            "recovery_strategy": recovery_strategy,
            "path": str(self.root_path),
            "status": status.get("status"),
            "runtime_status": status,
            "validated": validation["validated"],
            "health": validation["health"],
            "validation_error": validation["error"],
            "config": env.config,
            "cleanup_policy": self._get_isolation_manager().cleanup_policy,
        }

    def _get_isolation_validation(self, env: Any) -> dict[str, Any]:
        try:
            engine = env.isolation_engine
            validated = engine.validate_isolation(env)
            health = engine.check_environment_health(env)
            return {
                "validated": validated,
                "health": health,
                "error": None,
            }
        except Exception as exc:
            return {
                "validated": False,
                "health": False,
                "error": str(exc),
            }

    def _remove_path(self, path: Path) -> None:
        if not path.exists():
            return
        if path.is_dir():
            shutil.rmtree(path)
            return
        path.unlink()
