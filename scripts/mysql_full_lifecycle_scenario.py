#!/usr/bin/env python3
"""可重复执行的 MySQL 全生命周期实践入口。"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from ptest.api import PTestAPI


DEFAULT_OBJECT_NAME = "mysql_demo"
DEFAULT_CASE_NAME = "mysql_full_lifecycle_crud"
DEFAULT_REPORT_FORMAT = "json"
DEFAULT_DATABASE_NAME = "ptest_mysql_demo"


def _build_crud_case(object_name: str, database_name: str) -> dict[str, Any]:
    return {
        "type": "database",
        "object_name": object_name,
        "operations": [
            {
                "name": "create_database",
                "query": f"CREATE DATABASE IF NOT EXISTS {database_name}",
            },
            {
                "name": "use_database",
                "query": f"USE {database_name}",
            },
            {
                "name": "create_table",
                "query": (
                    "CREATE TABLE IF NOT EXISTS crud_items "
                    "(id INT PRIMARY KEY, name VARCHAR(32))"
                ),
            },
            {
                "name": "insert",
                "query": "INSERT INTO crud_items VALUES (1, 'alpha')",
                "expected_result": {"count": 1},
            },
            {
                "name": "select_after_insert",
                "query": "SELECT id, name FROM crud_items",
                "expected_result": [{"id": 1, "name": "alpha"}],
            },
            {
                "name": "update",
                "query": "UPDATE crud_items SET name = 'beta' WHERE id = 1",
                "expected_result": {"count": 1},
            },
            {
                "name": "select_after_update",
                "query": "SELECT id, name FROM crud_items",
                "expected_result": [{"id": 1, "name": "beta"}],
            },
            {
                "name": "delete",
                "query": "DELETE FROM crud_items WHERE id = 1",
                "expected_result": {"count": 1},
            },
            {
                "name": "select_after_delete",
                "query": "SELECT COUNT(*) AS count FROM crud_items",
                "expected_result": {"count": 0},
            },
        ],
    }


def _print_step(title: str, payload: dict[str, Any]) -> None:
    print(f"\n[{title}]")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _require_success(title: str, payload: dict[str, Any]) -> dict[str, Any]:
    _print_step(title, payload)
    if payload.get("success") is True:
        return payload
    raise RuntimeError(
        f"{title} 失败: {payload.get('message') or payload.get('error') or payload}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "执行 MySQL install -> start -> use -> stop -> uninstall 全流程案例。"
            "当前主案例基于 host runtime backend，要求执行环境允许真实进程启动和"
            " TCP 端口绑定。"
        ),
    )
    parser.add_argument(
        "--package-path",
        required=True,
        help="MySQL 8.4.8 安装包路径，例如 deb-bundle.tar",
    )
    parser.add_argument(
        "--workspace",
        required=True,
        help="本次案例使用的受管工作区路径；MySQL 实例目录会落在该路径下",
    )
    parser.add_argument(
        "--dependency-asset",
        action="append",
        default=[],
        help=(
            "依赖资产路径，可重复传入，例如 libaio / libnuma 的 .deb 包；"
            "依赖会安装到受管目录，不依赖宿主机全局库"
        ),
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="可选，MySQL 实例运行端口；建议显式指定，避免与宿主机已有服务冲突",
    )
    parser.add_argument(
        "--object-name",
        default=DEFAULT_OBJECT_NAME,
        help=f"可选，默认对象名为 {DEFAULT_OBJECT_NAME}",
    )
    parser.add_argument(
        "--case-name",
        default=DEFAULT_CASE_NAME,
        help=f"可选，默认 case 名为 {DEFAULT_CASE_NAME}",
    )
    parser.add_argument(
        "--database-name",
        default=DEFAULT_DATABASE_NAME,
        help=f"可选，主案例显式创建并使用的数据库名，默认 {DEFAULT_DATABASE_NAME}",
    )
    parser.add_argument(
        "--report-format",
        default=DEFAULT_REPORT_FORMAT,
        choices=["json", "html", "xml", "junit"],
        help="可选，案例结束后生成的报告格式",
    )
    parser.add_argument(
        "--destroy-environment",
        action="store_true",
        help="案例完成后销毁工作区环境元数据",
    )
    parser.add_argument(
        "--clean-workspace",
        action="store_true",
        help="在 destroy_environment 之后额外删除整个工作区目录",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    package_path = Path(args.package_path).expanduser().resolve()
    workspace = Path(args.workspace).expanduser().resolve()
    dependency_assets = [
        {"path": str(Path(item).expanduser().resolve())}
        for item in args.dependency_asset
    ]

    api = PTestAPI(work_path=workspace)
    execution_id: str | None = None
    report_path: str | None = None

    try:
        _require_success("init_environment", api.init_environment(path=workspace))

        install_kwargs: dict[str, Any] = {
            "mysql_package_path": str(package_path),
            "workspace_path": str(workspace),
        }
        if args.port is not None:
            install_kwargs["port"] = args.port
        if dependency_assets:
            install_kwargs["dependency_assets"] = dependency_assets

        _require_success(
            "install_object",
            api.create_object("mysql", args.object_name, **install_kwargs),
        )
        _require_success("start_object", api.start_object(args.object_name))
        _require_success("get_object_status", api.get_object_status(args.object_name))

        case_result = _require_success(
            "create_test_case",
            api.create_test_case(
                test_type="database",
                name=args.case_name,
                description="MySQL 全生命周期主案例 - 显式建库 / 用库 / CRUD",
                content=_build_crud_case(args.object_name, args.database_name),
                tags=["mysql", "lifecycle", "crud", "scenario"],
            ),
        )
        case_id = str(case_result["data"]["case_id"])

        _require_success("run_test_case", api.run_test_case(case_id))
        execution_records = api.list_execution_records(case_id=case_id)
        _print_step(
            "list_execution_records",
            execution_records,
        )
        records = execution_records.get("data")
        if isinstance(records, list) and records:
            latest = records[0]
            if isinstance(latest, dict):
                value = latest.get("execution_id")
                if value:
                    execution_id = str(value)

        report_result = api.generate_report(format_type=args.report_format)
        _print_step(
            "generate_report",
            report_result,
        )
        report_data = report_result.get("data")
        if isinstance(report_data, dict):
            path_value = report_data.get("report_path")
            if path_value:
                report_path = str(path_value)
        _print_step("list_problem_records", api.list_problem_records(case_id=case_id))

    finally:
        stop_result = api.stop_object(args.object_name)
        _print_step("stop_object", stop_result)

        uninstall_result = api.uninstall_object(args.object_name)
        _print_step("uninstall_object", uninstall_result)

        if args.destroy_environment:
            destroy_result = api.destroy_environment()
            _print_step("destroy_environment", destroy_result)

        if args.clean_workspace and workspace.exists():
            shutil.rmtree(workspace)
            print(f"\n[clean_workspace]\n已删除工作区: {workspace}")

    print("\n[summary]")
    print(
        json.dumps(
            {
                "workspace": str(workspace),
                "runtime_backend": "host",
                "package_path": str(package_path),
                "object_name": args.object_name,
                "case_name": args.case_name,
                "execution_id": execution_id,
                "report_path": report_path,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
