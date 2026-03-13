from __future__ import annotations

import socket
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
from ..models import EnvironmentRecord, ExecutionRecord, ManagedObjectRecord, ToolRecord
from ..mock import MockConfig, MockServer
from ..objects.manager import ObjectManager
from ..reports.generator import ReportGenerator
from ..suites import SuiteManager
from ..storage import WorkspaceStorage
from ..tools.manager import ToolManager


class WorkflowService:
    """First-phase workflow orchestration service."""

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

        env_manager = self._bootstrap_environment()
        existing = self.storage.load_environment()
        isolation_metadata = self._ensure_isolation_environment(existing)
        default_isolation_level = self.config.get("default_isolation_level", "basic")
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
            created_at=existing.created_at if existing else datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            metadata={
                "reports_dir": str(env_manager.report_dir),
                "logs_dir": str(env_manager.log_dir),
                "isolation": isolation_metadata,
            },
        )
        return self.storage.save_environment(record)

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
        normalized_type = manager.normalize_type(obj_type)
        result = manager.install(normalized_type, name, params or {})
        success = result.startswith("✓")
        materialized = manager.get_object(name) if success else None
        record = ManagedObjectRecord(
            name=name,
            type_name=normalized_type,
            status="installed" if success else "error",
            installed=success,
            config=params or {},
            created_at=self._existing_object_created_at(name),
            updated_at=datetime.now().isoformat(),
            metadata=self._collect_object_metadata(materialized)
            if materialized
            else {},
        )
        self.storage.upsert_object(record)
        return self._operation_result(
            success=success,
            status=record.status if success else "error",
            message=result,
            data=record.to_dict(),
            object=record.to_dict(),
            error_code="object_install_failed" if not success else None,
        )

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
        if success:
            self.storage.delete_object(name)
        else:
            record.status = "error"
            record.updated_at = datetime.now().isoformat()
            self.storage.upsert_object(record)
        return self._operation_result(
            success=success,
            status="removed" if success else "error",
            message=result,
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
        return self._operation_result(
            success=True,
            status=record.status,
            message=f"Object '{name}' status retrieved",
            data=record.to_dict(),
            object=record.to_dict(),
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
        result = case_manager.run_case(case_id, params=params)
        self._persist_execution(case_id, result, case_manager)
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
                    func=lambda case_id=case_id: case_manager.run_case(case_id),
                    timeout=float(timeout or 300),
                )
                for case_id in case_ids
            ]
            execution_results = executor.execute(tasks)
            executor.shutdown()
            results: list[dict[str, Any]] = []
            for execution_result in execution_results:
                case_result = execution_result.result
                if isinstance(case_result, TestCaseResult):
                    self._persist_execution(
                        case_result.case_id, case_result, case_manager
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
                func=lambda case_id=case_id: case_manager.run_case(case_id),
            )
            for case_id in case_ids
        ]
        execution_results = seq_executor.execute(tasks)
        results = []
        for execution_result in execution_results:
            case_result = execution_result.result
            if isinstance(case_result, TestCaseResult):
                self._persist_execution(case_result.case_id, case_result, case_manager)
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
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            return False

    def _change_object_state(self, name: str, action: str) -> dict[str, Any]:
        record = self.storage.get_object(name)
        if record is None:
            return self._not_found_result("object", name)

        obj = self._materialize_object(record)
        if record.type_name in {"database", "database_server", "database_client"}:
            self._recover_object_runtime(obj, record)
        operation = getattr(obj, action)
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
        metadata = record.metadata.copy()
        metadata.update(self._collect_object_metadata(obj))
        record.metadata = metadata
        record.updated_at = datetime.now().isoformat()
        self.storage.upsert_object(record)
        return self._operation_result(
            success=success,
            status=record.status,
            message=result,
            data=record.to_dict(),
            object=record.to_dict(),
            error_code=f"object_{action}_failed" if not success else None,
        )

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
                if record.status == "running":
                    start_result = obj.start()
                    if not (
                        isinstance(start_result, str) and start_result.startswith("✓")
                    ):
                        effective_status = "installed"
                        recovery["recovered"] = False
                        warnings.append(
                            "Database runtime could not be resumed; downgraded to installed"
                        )
            else:
                effective_status = "error"
                recovery["recovered"] = False
                warnings.append(str(install_result))
        elif (
            record.type_name == "database_server" and record.installed and record.config
        ):
            install_result = obj.install(record.config)
            if isinstance(install_result, str) and install_result.startswith("✓"):
                recovery["mode"] = "rebuild_server_component"
                component = getattr(obj, "server_component", None)
                if record.status == "running" and component is not None:
                    component.status = "running"
                    success, message = component.health_check()
                    if success:
                        obj.status = "running"
                    else:
                        obj.status = "installed"
                        effective_status = "installed"
                        recovery["recovered"] = False
                        warnings.append(message)
            else:
                effective_status = "error"
                recovery["recovered"] = False
                warnings.append(str(install_result))
        elif (
            record.type_name == "database_client" and record.installed and record.config
        ):
            install_result = obj.install(record.config)
            if isinstance(install_result, str) and install_result.startswith("✓"):
                recovery["mode"] = "rebuild_client_connection"
                if record.status == "running":
                    start_result = obj.start()
                    if not (
                        isinstance(start_result, str) and start_result.startswith("✓")
                    ):
                        effective_status = "installed"
                        recovery["recovered"] = False
                        warnings.append(
                            "Database client connection could not be resumed"
                        )
            else:
                effective_status = "error"
                recovery["recovered"] = False
                warnings.append(str(install_result))
        elif record.status == "running":
            effective_status = "installed" if record.installed else "stopped"
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

    def _persist_execution(
        self, case_id: str, result: TestCaseResult, case_manager: CaseManager
    ) -> ExecutionRecord:
        execution_id = f"{case_id}_{uuid.uuid4().hex[:12]}"
        environment = self.get_environment_status()
        objects = self.list_objects()
        case_definition = case_manager.get_case(case_id)
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
        return self.storage.save_execution(record)

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
