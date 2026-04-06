from __future__ import annotations

import ast
import os
import socket
import time
import uuid
from datetime import datetime
from pathlib import Path
import shutil
from typing import Any, cast

from ..cases.manager import CaseManager
from ..cases.result import TestCaseResult
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
    OBJECT_STATUS_ERROR,
    OBJECT_STATUS_INSTALL_FAILED_PRESERVED,
    OBJECT_STATUS_INSTALLED,
    OBJECT_STATUS_RUNNING,
    OBJECT_STATUS_START_FAILED_PRESERVED,
    OBJECT_STATUS_STOPPED,
    ToolRecord,
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


class WorkflowService:
    """First-phase workflow orchestration service."""

    DEFAULT_MANAGED_MYSQL_PORT = 13306

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
                    "isolation": isolation_metadata,
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
                "instance_name": name,
                "database_name": scenario.database_name,
                "data_dir": directories["data_dir"],
                "config_dir": directories["config_dir"],
                "config_file": str(Path(directories["config_dir"]) / "my.cnf"),
                "log_file": str(Path(directories["log_dir"]) / "mysql.log"),
                "pid_file": str(Path(directories["run_dir"]) / "mysql.pid"),
                "socket_file": str(Path(directories["run_dir"]) / "mysql.sock"),
                "managed_instance": directories,
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
        result = suite_manager.execute_suite(
            suite_name=name,
            case_manager=case_manager,
            parallel=parallel,
            max_workers=workers,
            stop_on_failure=stop_on_failure,
            timeout=timeout,
            retry_count=retry_count,
        )
        for case_id, case_result in case_manager.results.items():
            self._persist_execution(case_id, case_result, case_manager)
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
        result, case_definition = self._execute_case_with_bindings(
            case_manager,
            case_id,
            params=params,
        )
        self._persist_execution(
            case_id,
            result,
            case_manager,
            case_definition_override=case_definition,
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
                    func=lambda case_id=case_id: self._execute_case_with_bindings(
                        case_manager,
                        case_id,
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
                if isinstance(case_result, tuple) and len(case_result) == 2:
                    case_result, case_definition = case_result
                if isinstance(case_result, TestCaseResult):
                    self._persist_execution(
                        case_result.case_id,
                        case_result,
                        case_manager,
                        case_definition_override=case_definition,
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
                func=lambda case_id=case_id: self._execute_case_with_bindings(
                    case_manager,
                    case_id,
                ),
            )
            for case_id in case_ids
        ]
        execution_results = seq_executor.execute(tasks)
        results = []
        for execution_result in execution_results:
            case_result = execution_result.result
            case_definition = None
            if isinstance(case_result, tuple) and len(case_result) == 2:
                case_result, case_definition = case_result
            if isinstance(case_result, TestCaseResult):
                self._persist_execution(
                    case_result.case_id,
                    case_result,
                    case_manager,
                    case_definition_override=case_definition,
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

    def list_problem_records(
        self,
        *,
        problem_type: str | None = None,
        case_id: str | None = None,
        execution_id: str | None = None,
    ) -> list[dict[str, Any]]:
        records = self.storage.load_problem_records().values()
        filtered = []
        for record in records:
            if problem_type is not None and record.problem_type != problem_type:
                continue
            if case_id is not None and record.case_id != case_id:
                continue
            if execution_id is not None and record.execution_id != execution_id:
                continue
            filtered.append(record.to_dict())
        return sorted(filtered, key=lambda item: item["created_at"], reverse=True)

    def get_problem_record(self, problem_id: str) -> dict[str, Any]:
        record = self.storage.get_problem_record(problem_id)
        if record is None:
            return self._not_found_result("problem", problem_id)
        return self._operation_result(
            success=True,
            status="ok",
            message=f"Problem '{problem_id}' retrieved",
            data=record.to_dict(),
            problem=record.to_dict(),
        )

    def get_problem_assets(self, problem_id: str) -> dict[str, Any]:
        assets = self.storage.get_problem_assets(problem_id)
        if assets is None:
            return self._not_found_result("problem_assets", problem_id)
        return self._operation_result(
            success=True,
            status="ok",
            message=f"Assets for problem '{problem_id}' retrieved",
            data=assets.to_dict(),
            assets=assets.to_dict(),
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
        if assets.problem_type != "api_response":
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
            return failure, case_definition
        return case_manager.run_case(case_id, params=resolved_params), case_definition

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
    ) -> ExecutionRecord:
        execution_id = f"{case_id}_{uuid.uuid4().hex[:12]}"
        environment = self.get_environment_status()
        objects = self.list_objects()
        case_definition = case_definition_override or case_manager.get_case(case_id)
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
            },
        )
        artifacts = self.storage.save_execution_artifacts(
            execution_id,
            environment=environment,
            objects=objects,
            case=case_definition,
            result=result_payload,
            output=result.output,
        )
        record.metadata["artifacts"] = artifacts
        record.metadata["artifacts"] = self.storage.save_execution_artifact_record(
            record
        )
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
        )
        if built is None:
            return
        problem_record, problem_assets = built

        self.storage.save_problem_record(problem_record)
        self.storage.save_problem_assets(problem_assets)
        problems = record.metadata.setdefault("problems", [])
        if isinstance(problems, list):
            problems.append(problem_record.to_dict())
            self.storage.save_execution(record)

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
    ) -> tuple[ProblemRecord, ProblemAssetRecord] | None:
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
        problem_record = ProblemRecord(
            problem_id=problem_id,
            problem_type="api_response",
            summary=summary,
            status="open",
            preservation_status="success",
            execution_id=record.execution_id,
            case_id=record.case_id,
            environment_id=environment_id,
            object_refs=object_refs,
            artifact_refs=self._problem_artifact_refs(artifact_refs),
            log_refs=log_refs,
            latest_action="preserved",
            created_at=now,
            updated_at=now,
            metadata={"source": "execution_failure"},
        )
        observed_response = {
            "output": record.output,
            "error": record.error_message,
            "status": record.status,
        }
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
                        problem_record.artifact_refs.get("execution_artifacts")
                        or problem_record.artifact_refs.get("artifact_index")
                    ),
                    "execution artifacts were not preserved",
                ),
                "log_index": (
                    bool(log_refs.get("workspace_logs_dir")),
                    "log index is not available",
                ),
            }
        )
        problem_record.preservation_status = preservation["status"]
        problem_record.metadata["preservation"] = preservation
        problem_assets = ProblemAssetRecord(
            problem_id=problem_id,
            problem_type="api_response",
            summary=summary,
            status="open",
            preservation_status=preservation["status"],
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
            details={
                "request": request_payload,
                "response": observed_response,
                "case": case_payload,
                "preservation": preservation,
            },
            created_at=now,
            updated_at=now,
            metadata={"source_execution": record.execution_id},
        )
        return problem_record, problem_assets

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
        recovery_hints = {
            "supported": False,
            "mode": "minimal_state_hints",
            "db_type": case_payload.get("db_type", "unknown"),
            "database": database_path,
            "query": case_payload.get("query", ""),
            "expected_result": case_payload.get("expected_result"),
        }
        actual_result = self._extract_data_actual_result(record)
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
            "error": record.error_message,
            "case": case_payload,
        }
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
            }
        )
        problem_record = ProblemRecord(
            problem_id=problem_id,
            problem_type="data_state",
            summary=summary,
            status="open",
            preservation_status=preservation["status"],
            execution_id=record.execution_id,
            case_id=record.case_id,
            environment_id=environment_id,
            object_refs=object_refs,
            artifact_refs=self._problem_artifact_refs(artifact_refs),
            log_refs=log_refs,
            latest_action="preserved",
            created_at=now,
            updated_at=now,
            metadata={
                "source": "execution_failure",
                "preservation": preservation,
            },
        )
        problem_assets = ProblemAssetRecord(
            problem_id=problem_id,
            problem_type="data_state",
            summary=summary,
            status="open",
            preservation_status=preservation["status"],
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
            metadata={"source_execution": record.execution_id},
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
        recovery = {
            "supported": False,
            "mode": "basic_runtime_validation",
            "service_name": service_name,
            "host": case_payload.get("host", "localhost"),
            "port": case_payload.get("port", 8080),
            "check_type": case_payload.get("check_type", "port"),
        }
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
        problem_record = ProblemRecord(
            problem_id=problem_id,
            problem_type="service_runtime",
            summary=summary,
            status="open",
            preservation_status=preservation["status"],
            execution_id=record.execution_id,
            case_id=record.case_id,
            environment_id=environment_id,
            object_refs=runtime_object_refs,
            artifact_refs=self._problem_artifact_refs(artifact_refs),
            log_refs=log_refs,
            latest_action="preserved",
            created_at=now,
            updated_at=now,
            metadata={
                "source": "execution_failure",
                "preservation": preservation,
            },
        )
        problem_assets = ProblemAssetRecord(
            problem_id=problem_id,
            problem_type="service_runtime",
            summary=summary,
            status="open",
            preservation_status=preservation["status"],
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
            metadata={"source_execution": record.execution_id},
        )
        return problem_record, problem_assets

    def _build_service_runtime_problem_summary(self, record: ExecutionRecord) -> str:
        error = record.error_message.strip() or "Execution failed"
        return f"Service runtime problem for case '{record.case_id}': {error}"

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

    def _build_recovery_plan(
        self, record: ProblemRecord, assets: ProblemAssetRecord
    ) -> dict[str, Any]:
        if assets.problem_type == "api_response":
            return self._build_api_recovery_plan(record, assets)
        if assets.problem_type == "data_state":
            return self._build_data_recovery_plan(record, assets)
        if assets.problem_type in {
            "environment_init",
            "dependency_object",
            "dependency_configuration",
        }:
            return self._build_environment_dependency_recovery_plan(record, assets)
        if assets.problem_type == "service_runtime":
            return self._build_service_runtime_recovery_plan(record, assets)

        recovery = assets.recovery if isinstance(assets.recovery, dict) else {}
        return {
            "problem_id": record.problem_id,
            "problem_type": record.problem_type,
            "summary": record.summary,
            "supported": bool(recovery.get("supported", False)),
            "mode": recovery.get("mode", "unsupported"),
            "steps": [],
            "hints": recovery,
        }

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
        return {
            "problem_id": record.problem_id,
            "problem_type": record.problem_type,
            "summary": record.summary,
            "supported": bool(recovery.get("supported", False)),
            "mode": recovery.get("mode", "minimal_state_hints"),
            "steps": [
                "Verify the target database or data source is reachable.",
                "Recreate or inspect the minimal precondition data before rerunning the query.",
                "Run the preserved query and compare actual vs expected results.",
            ],
            "data_source": data_source if isinstance(data_source, dict) else {},
            "operations": operations if isinstance(operations, list) else [],
            "expected_result": details.get("expected_result"),
            "actual_result": details.get("actual_result"),
            "hints": recovery,
        }

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
        return {
            "problem_id": record.problem_id,
            "problem_type": record.problem_type,
            "summary": record.summary,
            "supported": bool(recovery.get("supported", False)),
            "mode": recovery.get("mode", "basic_runtime_validation"),
            "steps": [
                "Inspect the preserved service endpoint and runtime failure message.",
                "Verify the target service process or port is reachable.",
                "Retry the minimal runtime validation against the same host and port.",
            ],
            "service": service if isinstance(service, dict) else {},
            "runtime_result": runtime_result
            if isinstance(runtime_result, dict)
            else {},
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
        problem_record = ProblemRecord(
            problem_id=problem_id,
            problem_type=problem_type,
            summary=summary,
            status="open",
            preservation_status=preservation["status"],
            execution_id="",
            case_id="",
            environment_id=env_context["environment_id"],
            object_refs=refs,
            artifact_refs={},
            log_refs=env_context["log_refs"],
            latest_action="preserved",
            created_at=now,
            updated_at=now,
            metadata={
                "source": "environment_dependency",
                "preservation": preservation,
            },
        )
        problem_assets = ProblemAssetRecord(
            problem_id=problem_id,
            problem_type=problem_type,
            summary=summary,
            status="open",
            preservation_status=preservation["status"],
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
        self.storage.save_problem_record(problem_record)
        self.storage.save_problem_assets(problem_assets)
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
        self.storage.save_problem_recovery(recovery_record)

        latest_recovery = {
            "action_id": action_id,
            "action_type": action_type,
            "status": status,
            "mode": mode,
            "success": success,
            "created_at": now,
        }
        record.latest_action = f"{action_type}:{status}"
        record.updated_at = now
        record.metadata["latest_recovery"] = latest_recovery
        assets.metadata["latest_recovery"] = latest_recovery
        assets.updated_at = now

        self.storage.save_problem_record(record)
        self.storage.save_problem_assets(assets)
        return recovery_record

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
