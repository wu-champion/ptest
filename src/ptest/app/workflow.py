from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
import shutil
from typing import Any

from ..cases.manager import CaseManager
from ..cases.result import TestCaseResult
from ..config import DEFAULT_CONFIG
from ..environment import EnvironmentManager
from ..isolation.manager import IsolationManager
from ..models import EnvironmentRecord, ExecutionRecord, ManagedObjectRecord, ToolRecord
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

    def init_environment(self, path: str | Path | None = None) -> EnvironmentRecord:
        if path is not None:
            self.root_path = Path(path).resolve()
            self.storage = WorkspaceStorage(self.root_path)

        env_manager = self._bootstrap_environment()
        existing = self.storage.load_environment()
        isolation_metadata = self._ensure_isolation_environment(existing)
        record = EnvironmentRecord(
            root_path=str(self.root_path),
            status="ready",
            isolation_level=self.config.get("default_isolation_level", "basic"),
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
        record = ManagedObjectRecord(
            name=name,
            type_name=normalized_type,
            status="installed" if success else "error",
            installed=success,
            config=params or {},
            created_at=self._existing_object_created_at(name),
            updated_at=datetime.now().isoformat(),
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
        return [record.to_dict() for record in objects.values()]

    def get_object_status(self, name: str) -> dict[str, Any]:
        record = self.storage.get_object(name)
        if record is None:
            return self._not_found_result("object", name)
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
        result.setdefault("error", None if result.get("success") else result.get("results"))
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
                    self._persist_execution(case_result.case_id, case_result, case_manager)
                    results.append(self._result_payload(case_result))
            return self._summarize_results(results)

        executor = SequentialExecutor(
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
        execution_results = executor.execute(tasks)
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

    def _get_isolation_manager(self) -> IsolationManager:
        if self._isolation_manager is None:
            self._isolation_manager = IsolationManager(self.config)
        return self._isolation_manager

    def _change_object_state(self, name: str, action: str) -> dict[str, Any]:
        record = self.storage.get_object(name)
        if record is None:
            return self._not_found_result("object", name)

        obj = self._materialize_object(record)
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

    def _materialize_object(self, record: ManagedObjectRecord):
        manager = self._get_object_manager()
        obj = manager.create_object(record.type_name, record.name, record.config)
        if hasattr(obj, "installed"):
            obj.installed = record.installed
        if hasattr(obj, "status"):
            obj.status = record.status
        if hasattr(obj, "db_config") and record.config:
            obj.db_config = record.config.copy()
        return obj

    def _materialize_tool(self, record: ToolRecord):
        manager = self._get_tool_manager()
        tool = manager.install(record.name, record.config)
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
        saved_record = self.storage.save_execution(record)
        self.storage.save_execution_artifact_record(saved_record)
        return saved_record

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
        isolation_level = self.config.get("default_isolation_level", "basic")
        existing_metadata = existing.metadata.get("isolation", {}) if existing else {}
        env_id = existing_metadata.get("env_id")
        env_config = existing_metadata.get("config", {})

        if env_id:
            env = self._attach_isolation_environment(env_id, isolation_level, env_config)
            return self._isolation_metadata(env, isolation_level, attached=True)

        env = manager.create_environment(
            self.root_path,
            isolation_level=isolation_level,
            env_config=env_config or None,
        )
        env.activate()
        return self._isolation_metadata(env, isolation_level, attached=False)

    def _attach_isolation_environment(
        self,
        env_id: str,
        isolation_level: str,
        env_config: dict[str, Any] | None = None,
    ):
        manager = self._get_isolation_manager()
        attached = manager.get_environment(env_id)
        if attached is not None:
            return attached

        engine = manager.engines.get(isolation_level)
        if engine is None:
            engine = manager.registry.create_engine(
                isolation_level,
                self.config.get(isolation_level, {}),
            )
            if engine is not None:
                manager.engines[isolation_level] = engine
        if engine is None:
            raise ValueError(f"Unsupported isolation level: {isolation_level}")

        isolation_config = (env_config or {}).copy()
        isolation_config.update(self.config.get(isolation_level, {}))
        env = engine.create_isolation(self.root_path, env_id, isolation_config)
        manager.active_environments[env_id] = env
        if not hasattr(engine, "created_environments"):
            engine.created_environments = {}
        engine.created_environments[env_id] = env
        env.activate()
        return env

    def _cleanup_isolation_environment(
        self,
        record: EnvironmentRecord,
    ) -> dict[str, Any]:
        isolation = record.metadata.get("isolation", {})
        env_id = isolation.get("env_id")
        isolation_level = isolation.get("isolation_level", record.isolation_level)
        env_config = isolation.get("config", {})
        if not env_id:
            return {"success": False, "skipped": True, "messages": []}

        manager = self._get_isolation_manager()
        messages: list[str] = []
        try:
            env = self._attach_isolation_environment(env_id, isolation_level, env_config)
            deactivated = env.deactivate()
            messages.append(
                f"Isolation environment '{env_id}' deactivated"
                if deactivated
                else f"Isolation environment '{env_id}' deactivation skipped"
            )
            cleaned = env.cleanup(force=False)
            if env_id in manager.active_environments:
                del manager.active_environments[env_id]
            engine = manager.engines.get(isolation_level)
            if engine is not None and env_id in engine.created_environments:
                del engine.created_environments[env_id]
            messages.append(
                f"Isolation environment '{env_id}' cleanup completed"
                if cleaned
                else f"Isolation environment '{env_id}' cleanup reported failure"
            )
            return {
                "success": cleaned,
                "skipped": False,
                "env_id": env_id,
                "messages": messages,
            }
        except Exception as exc:
            messages.append(
                f"Isolation environment '{env_id}' cleanup failed: {exc}"
            )
            return {
                "success": False,
                "skipped": False,
                "env_id": env_id,
                "messages": messages,
                "error": str(exc),
            }

    def _isolation_metadata(
        self,
        env: Any,
        isolation_level: str,
        *,
        attached: bool,
    ) -> dict[str, Any]:
        status = env.get_status()
        return {
            "env_id": env.env_id,
            "isolation_level": isolation_level,
            "attached": attached,
            "path": str(self.root_path),
            "status": status.get("status"),
            "config": env.config,
        }

    def _remove_path(self, path: Path) -> None:
        if not path.exists():
            return
        if path.is_dir():
            shutil.rmtree(path)
            return
        path.unlink()
