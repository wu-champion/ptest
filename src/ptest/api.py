# ptest/api.py - Python API 接口

from __future__ import annotations

import time
import uuid
from pathlib import Path
from types import TracebackType
from typing import Any

from .app import WorkflowService
from .config import DEFAULT_CONFIG
from .core import get_logger
from .isolation.manager import IsolationManager

logger = get_logger("api")


class PTestAPI:
    """ptest Python API - 基于统一工作流服务的编程接口"""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        work_path: str | Path | None = None,
    ) -> None:
        self.config = config.copy() if config else DEFAULT_CONFIG.copy()
        self.work_path = Path(work_path).resolve() if work_path else Path.cwd()
        self.workflow = WorkflowService(self.work_path, self.config)
        self.isolation_manager = IsolationManager(self.config)
        logger.info("PTest API initialized")

    def init_environment(self, path: str | Path | None = None) -> dict[str, Any]:
        record = self.workflow.init_environment(path or self.work_path)
        self.work_path = Path(record.root_path)
        return self._api_response(
            success=True,
            status=record.status,
            message=f"Environment initialized at: {record.root_path}",
            data=record.to_dict(),
        )

    def get_environment_status(self) -> dict[str, Any]:
        status = self.workflow.get_environment_status()
        normalized_status = status.get(
            "status", "ready" if status.get("initialized") else "uninitialized"
        )
        return self._api_response(
            success=True,
            status=normalized_status,
            message=f"Environment status retrieved for: {status.get('path')}",
            data=status,
        )

    def create_test_case(
        self,
        test_type: str,
        name: str,
        description: str = "",
        content: Any = None,
        tags: list[str] | None = None,
        expected_result: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        self.workflow.init_environment(self.work_path)
        case_id = f"{test_type}_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        case_data = {
            "type": test_type,
            "name": name,
            "description": description,
            "tags": tags or [],
            "expected_result": expected_result,
            "timeout": timeout,
        }
        if isinstance(content, dict):
            case_data.update(content)
        elif content is not None:
            case_data["content"] = content
        result = self.workflow.add_case(case_id, case_data)
        return self._api_response(
            success=result["success"],
            status=result["status"],
            message=result["message"],
            data={"case_id": case_id, "case": case_data},
            error=result.get("error"),
            error_code=result.get("error_code"),
        )

    def list_test_cases(self) -> dict[str, Any]:
        cases = self.workflow.list_cases()
        return self._api_response(
            success=True,
            status="ok",
            message=f"Retrieved {len(cases)} test cases",
            data=cases,
        )

    def run_test_case(
        self, case_id: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        result = self.workflow.run_case(case_id, params=params)
        return self._api_response(
            success=result["success"],
            status=result["status"],
            message=result["message"],
            data=result,
            error=result.get("error"),
        )

    def create_object(self, obj_type: str, name: str, **kwargs: Any) -> dict[str, Any]:
        return self.workflow.install_object(obj_type, name, kwargs)

    def list_objects(self) -> dict[str, Any]:
        objects = self.workflow.list_objects()
        return self._api_response(
            success=True,
            status="ok",
            message=f"Retrieved {len(objects)} objects",
            data=objects,
        )

    def install_tool(self, name: str, **kwargs: Any) -> dict[str, Any]:
        return self.workflow.install_tool(name, kwargs)

    def list_tools(self) -> dict[str, Any]:
        tools = self.workflow.list_tools()
        return self._api_response(
            success=True,
            status="ok",
            message=f"Retrieved {len(tools)} tools",
            data=tools,
        )

    def create_suite(self, suite_data: dict[str, Any]) -> dict[str, Any]:
        return self.workflow.create_suite(suite_data)

    def list_suites(self) -> dict[str, Any]:
        suites = self.workflow.list_suites()
        return self._api_response(
            success=True,
            status="ok",
            message=f"Retrieved {len(suites)} suites",
            data=suites,
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
        result = self.workflow.run_suite(
            name=name,
            parallel=parallel,
            workers=workers,
            stop_on_failure=stop_on_failure,
            timeout=timeout,
            retry_count=retry_count,
        )
        return self._api_response(
            success=result["success"],
            status=result["status"],
            message=result["message"],
            data=result,
            error=result.get("error"),
        )

    def generate_report(
        self,
        format_type: str = "html",
        output_path: str | Path | None = None,
    ) -> dict[str, Any]:
        report_path = self.workflow.generate_report(format_type, output_path)
        return self._api_response(
            success=True,
            status="generated",
            message=f"Report generated: {report_path}",
            data={"report_path": report_path, "format": format_type},
        )

    def list_execution_records(self, case_id: str | None = None) -> dict[str, Any]:
        records = self.workflow.list_execution_records(case_id=case_id)
        return self._api_response(
            success=True,
            status="ok",
            message=f"Retrieved {len(records)} execution records",
            data=records,
        )

    def get_execution_record(self, execution_id: str) -> dict[str, Any]:
        result = self.workflow.get_execution_record(execution_id)
        return self._api_response(
            success=result["success"],
            status=result["status"],
            message=result["message"],
            data=result.get("execution"),
            error=result.get("error"),
            error_code=result.get("error_code"),
        )

    def get_execution_artifacts(
        self,
        execution_id: str,
        *,
        include_contents: bool = False,
    ) -> dict[str, Any]:
        result = self.workflow.get_execution_artifacts(
            execution_id,
            include_contents=include_contents,
        )
        return self._api_response(
            success=result["success"],
            status=result["status"],
            message=result["message"],
            data=result.get("artifacts"),
            error=result.get("error"),
            error_code=result.get("error_code"),
        )

    def list_problem_records(
        self,
        *,
        problem_type: str | None = None,
        case_id: str | None = None,
        execution_id: str | None = None,
    ) -> dict[str, Any]:
        records = self.workflow.list_problem_records(
            problem_type=problem_type,
            case_id=case_id,
            execution_id=execution_id,
        )
        return self._api_response(
            success=True,
            status="ok",
            message=f"Retrieved {len(records)} problem records",
            data=records,
        )

    def get_problem_record(self, problem_id: str) -> dict[str, Any]:
        result = self.workflow.get_problem_record(problem_id)
        return self._api_response(
            success=result["success"],
            status=result["status"],
            message=result["message"],
            data=result.get("problem"),
            error=result.get("error"),
            error_code=result.get("error_code"),
        )

    def get_problem_assets(self, problem_id: str) -> dict[str, Any]:
        result = self.workflow.get_problem_assets(problem_id)
        return self._api_response(
            success=result["success"],
            status=result["status"],
            message=result["message"],
            data=result.get("assets"),
            error=result.get("error"),
            error_code=result.get("error_code"),
        )

    def get_problem_recovery(self, problem_id: str) -> dict[str, Any]:
        result = self.workflow.get_problem_recovery(problem_id)
        return self._api_response(
            success=result["success"],
            status=result["status"],
            message=result["message"],
            data=result.get("recovery_action"),
            error=result.get("error"),
            error_code=result.get("error_code"),
        )

    def replay_problem(self, problem_id: str) -> dict[str, Any]:
        result = self.workflow.replay_problem(problem_id)
        return self._api_response(
            success=result["success"],
            status=result["status"],
            message=result["message"],
            data=result.get("replay"),
            recovery_action=result.get("recovery_action"),
            error=result.get("error"),
            error_code=result.get("error_code"),
        )

    def recover_problem(self, problem_id: str) -> dict[str, Any]:
        result = self.workflow.recover_problem(problem_id)
        return self._api_response(
            success=result["success"],
            status=result["status"],
            message=result["message"],
            data=result.get("recovery"),
            recovery_action=result.get("recovery_action"),
            error=result.get("error"),
            error_code=result.get("error_code"),
        )

    def destroy_environment(self) -> dict[str, Any]:
        return self.workflow.destroy_environment()

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
        result = self.workflow.generate_data(
            data_type,
            count=count,
            locale=locale,
            format_type=format_type,
            table=table,
            dialect=dialect,
            batch_size=batch_size,
            seed=seed,
        )
        return self._api_response(
            success=result["success"],
            status=result["status"],
            message=result["message"],
            data=result.get("data"),
            error=result.get("error"),
            error_code=result.get("error_code"),
        )

    def save_data_template(
        self, name: str, definition: dict[str, Any]
    ) -> dict[str, Any]:
        result = self.workflow.save_data_template(name, definition)
        return self._api_response(
            success=result["success"],
            status=result["status"],
            message=result["message"],
            data=result.get("data"),
        )

    def list_data_templates(self) -> dict[str, Any]:
        result = self.workflow.list_data_templates()
        return self._api_response(
            success=True,
            status=result["status"],
            message=result["message"],
            data=result["data"],
        )

    def generate_data_from_template(
        self, name: str, *, count: int = 1
    ) -> dict[str, Any]:
        result = self.workflow.generate_data_from_template(name, count=count)
        return self._api_response(
            success=result["success"],
            status=result["status"],
            message=result["message"],
            data=result.get("data"),
            error=result.get("error"),
            error_code=result.get("error_code"),
        )

    def import_contract(self, source: str, name: str | None = None) -> dict[str, Any]:
        result = self.workflow.import_contract(source, name)
        return self._api_response(
            success=result["success"],
            status=result["status"],
            message=result["message"],
            data=result.get("data"),
        )

    def list_contracts(self) -> dict[str, Any]:
        result = self.workflow.list_contracts()
        return self._api_response(
            success=True,
            status=result["status"],
            message=result["message"],
            data=result["data"],
        )

    def generate_cases_from_contract(
        self, name: str, *, persist: bool = True
    ) -> dict[str, Any]:
        result = self.workflow.generate_cases_from_contract(name, persist=persist)
        return self._api_response(
            success=result["success"],
            status=result["status"],
            message=result["message"],
            data=result.get("data"),
            error=result.get("error"),
            error_code=result.get("error_code"),
        )

    def start_mock_server(
        self,
        name: str,
        *,
        port: int = 8080,
        host: str = "127.0.0.1",
        blocking: bool = False,
    ) -> dict[str, Any]:
        result = self.workflow.start_mock_server(
            name, port=port, host=host, blocking=blocking
        )
        return self._api_response(
            success=result["success"],
            status=result["status"],
            message=result["message"],
            data=result.get("data"),
            error=result.get("error"),
            error_code=result.get("error_code"),
        )

    def list_mock_servers(self) -> dict[str, Any]:
        result = self.workflow.list_mock_servers()
        return self._api_response(
            success=True,
            status=result["status"],
            message=result["message"],
            data=result["data"],
        )

    def get_system_info(self) -> dict[str, Any]:
        env_status = self.workflow.get_environment_status()
        return self._api_response(
            success=True,
            status="ok",
            message="System info retrieved",
            data={
                "version": "1.5.0",
                "api_version": "1.5.0",
                "work_path": str(self.work_path),
                "environment_initialized": env_status.get("initialized", False),
                "environment_path": env_status.get("path"),
                "isolation_engines": list(self.isolation_manager.engines.keys()),
                "framework_version": "PTEST-1.5.0",
            },
        )

    def __enter__(self) -> "PTestAPI":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        return None

    def _api_response(
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
            "work_path": str(self.work_path),
            "data": data,
        }
        payload.update(extra)
        return payload


def create_ptest_api(
    config: dict[str, Any] | None = None,
    work_path: str | Path | None = None,
) -> PTestAPI:
    """创建 PTestAPI 实例的便捷函数"""

    return PTestAPI(config=config, work_path=work_path)
