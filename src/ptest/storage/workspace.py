from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from ..models import (
    EnvironmentRecord,
    ExecutionRecord,
    ManagedObjectRecord,
    ProblemAssetRecord,
    ProblemRecoveryRecord,
    ProblemRecord,
    ToolRecord,
)


class WorkspaceStorage:
    """File-backed storage for the first-phase workflow."""

    def __init__(self, root_path: str | Path):
        self.root_path = Path(root_path).resolve()
        self.meta_dir = self.root_path / ".ptest"
        self.executions_dir = self.meta_dir / "executions"
        self.artifacts_dir = self.meta_dir / "artifacts"
        self.problems_dir = self.meta_dir / "problems"
        self.environment_file = self.meta_dir / "environment.json"
        self.objects_file = self.meta_dir / "objects.json"
        self.tools_file = self.meta_dir / "tools.json"
        self.problems_index_file = self.meta_dir / "problems.json"
        self.execution_problem_index_file = self.meta_dir / "execution_to_problems.json"
        self.case_problem_index_file = self.meta_dir / "case_to_problems.json"

    def ensure_layout(self) -> None:
        self.meta_dir.mkdir(parents=True, exist_ok=True)
        self.executions_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.problems_dir.mkdir(parents=True, exist_ok=True)

    def load_environment(self) -> EnvironmentRecord | None:
        data = self._read_json(self.environment_file)
        if not data:
            return None
        return EnvironmentRecord.from_dict(data)

    def save_environment(self, record: EnvironmentRecord) -> EnvironmentRecord:
        self.ensure_layout()
        self._write_json(self.environment_file, record.to_dict())
        return record

    def load_objects(self) -> dict[str, ManagedObjectRecord]:
        data = self._read_json(self.objects_file)
        if not data:
            return {}
        return {
            item["name"]: ManagedObjectRecord.from_dict(item)
            for item in data.get("objects", [])
        }

    def save_objects(self, objects: dict[str, ManagedObjectRecord]) -> None:
        self.ensure_layout()
        payload = {
            "objects": [record.to_dict() for record in objects.values()],
        }
        self._write_json(self.objects_file, payload)

    def upsert_object(self, record: ManagedObjectRecord) -> ManagedObjectRecord:
        objects = self.load_objects()
        objects[record.name] = record
        self.save_objects(objects)
        return record

    def delete_object(self, name: str) -> bool:
        objects = self.load_objects()
        if name not in objects:
            return False
        del objects[name]
        self.save_objects(objects)
        return True

    def get_object(self, name: str) -> ManagedObjectRecord | None:
        return self.load_objects().get(name)

    def load_tools(self) -> dict[str, ToolRecord]:
        data = self._read_json(self.tools_file)
        if not data:
            return {}
        return {
            item["name"]: ToolRecord.from_dict(item) for item in data.get("tools", [])
        }

    def save_tools(self, tools: dict[str, ToolRecord]) -> None:
        self.ensure_layout()
        payload = {
            "tools": [record.to_dict() for record in tools.values()],
        }
        self._write_json(self.tools_file, payload)

    def upsert_tool(self, record: ToolRecord) -> ToolRecord:
        tools = self.load_tools()
        tools[record.name] = record
        self.save_tools(tools)
        return record

    def delete_tool(self, name: str) -> bool:
        tools = self.load_tools()
        if name not in tools:
            return False
        del tools[name]
        self.save_tools(tools)
        return True

    def get_tool(self, name: str) -> ToolRecord | None:
        return self.load_tools().get(name)

    def save_execution(self, record: ExecutionRecord) -> ExecutionRecord:
        self.ensure_layout()
        self._write_json(
            self.executions_dir / f"{record.execution_id}.json",
            record.to_dict(),
        )
        return record

    def save_execution_artifacts(
        self,
        execution_id: str,
        *,
        environment: dict[str, Any],
        objects: list[dict[str, Any]],
        case: dict[str, Any] | None,
        result: dict[str, Any],
        output: Any = None,
    ) -> dict[str, Any]:
        self.ensure_layout()
        artifact_dir = self.artifacts_dir / execution_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        context_dir = artifact_dir / "context"
        case_dir = artifact_dir / "case"
        result_dir = artifact_dir / "result"
        output_dir = artifact_dir / "output"
        logs_dir = artifact_dir / "logs"
        indexes_dir = artifact_dir / "indexes"

        files = {
            "environment": self._write_artifact_file(
                context_dir / "environment.json",
                environment,
            ),
            "objects": self._write_artifact_file(
                context_dir / "objects.json",
                {"objects": objects},
            ),
            "case": self._write_artifact_file(
                case_dir / "case.json",
                case or {},
            ),
            "result": self._write_artifact_file(
                result_dir / "result.json",
                result,
            ),
        }

        if output not in (None, ""):
            output_path = output_dir / (
                "output.txt" if isinstance(output, str) else "output.json"
            )
            if isinstance(output, str):
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(output, encoding="utf-8")
                files["output"] = str(output_path.relative_to(self.root_path))
            else:
                files["output"] = self._write_artifact_file(output_path, output)

        categories = {
            "context": {
                "environment": files["environment"],
                "objects": files["objects"],
            },
            "case": {
                "case": files["case"],
            },
            "result": {
                "result": files["result"],
            },
            "output": {
                "output": files["output"],
            }
            if "output" in files
            else {},
        }
        log_index = {
            "execution_id": execution_id,
            "workspace_logs_dir": self._relative_workspace_path(
                self.root_path / "logs"
            ),
            "files": self._list_workspace_logs(),
            "generated_at": datetime.now().isoformat(),
        }
        log_index_path = self._write_artifact_file(
            logs_dir / "log_index.json",
            log_index,
        )
        indexes = {
            "artifact_index": str(
                (indexes_dir / "artifact_index.json").relative_to(self.root_path)
            ),
            "log_index": log_index_path,
        }
        artifact_manifest = {
            "execution_id": execution_id,
            "directory": str(artifact_dir.relative_to(self.root_path)),
            "files": files,
            "categories": categories,
            "indexes": indexes,
            "generated_at": datetime.now().isoformat(),
        }
        self._write_artifact_file(
            indexes_dir / "artifact_index.json", artifact_manifest
        )
        return artifact_manifest

    def save_execution_artifact_record(self, record: ExecutionRecord) -> dict[str, Any]:
        self.ensure_layout()
        artifact_dir = self.artifacts_dir / record.execution_id
        result_dir = artifact_dir / "result"
        execution_path = self._write_artifact_file(
            result_dir / "execution.json",
            record.to_dict(),
        )
        artifact_index_path = artifact_dir / "indexes" / "artifact_index.json"
        artifact_index = self._read_json(artifact_index_path) or {
            "execution_id": record.execution_id,
            "directory": str(artifact_dir.relative_to(self.root_path)),
            "files": {},
            "categories": {},
            "indexes": {
                "artifact_index": str(artifact_index_path.relative_to(self.root_path)),
            },
        }
        files = artifact_index.setdefault("files", {})
        files["execution"] = execution_path
        result_category = artifact_index.setdefault("categories", {}).setdefault(
            "result",
            {},
        )
        result_category["execution"] = execution_path
        artifact_index["updated_at"] = datetime.now().isoformat()
        self._write_json(artifact_index_path, artifact_index)
        return artifact_index

    def list_executions(self) -> list[ExecutionRecord]:
        self.ensure_layout()
        records: list[ExecutionRecord] = []
        for path in sorted(self.executions_dir.glob("*.json")):
            data = self._read_json(path)
            if data:
                records.append(ExecutionRecord.from_dict(data))
        return records

    def get_execution(self, execution_id: str) -> ExecutionRecord | None:
        self.ensure_layout()
        data = self._read_json(self.executions_dir / f"{execution_id}.json")
        if not data:
            return None
        return ExecutionRecord.from_dict(data)

    def load_problem_records(self) -> dict[str, ProblemRecord]:
        data = self._read_json(self.problems_index_file)
        if not data:
            return {}
        return {
            item["problem_id"]: ProblemRecord.from_dict(item)
            for item in data.get("problems", [])
        }

    def save_problem_records(self, problems: dict[str, ProblemRecord]) -> None:
        self.ensure_layout()
        payload = {
            "problems": [record.to_dict() for record in problems.values()],
        }
        self._write_json(self.problems_index_file, payload)

    def save_problem_record(self, record: ProblemRecord) -> ProblemRecord:
        problems = self.load_problem_records()
        problems[record.problem_id] = record
        self.save_problem_records(problems)
        self._write_json(
            self.problems_dir / record.problem_id / "record.json",
            record.to_dict(),
        )
        self._link_problem_indexes(
            record.problem_id, record.execution_id, record.case_id
        )
        return record

    def get_problem_record(self, problem_id: str) -> ProblemRecord | None:
        problem_path = self.problems_dir / problem_id / "record.json"
        data = self._read_json(problem_path)
        if data:
            return ProblemRecord.from_dict(data)
        return self.load_problem_records().get(problem_id)

    def save_problem_assets(self, record: ProblemAssetRecord) -> ProblemAssetRecord:
        self.ensure_layout()
        self._write_json(
            self.problems_dir / record.problem_id / "assets.json",
            record.to_dict(),
        )
        return record

    def get_problem_assets(self, problem_id: str) -> ProblemAssetRecord | None:
        data = self._read_json(self.problems_dir / problem_id / "assets.json")
        if not data:
            return None
        return ProblemAssetRecord.from_dict(data)

    def save_problem_recovery(
        self, record: ProblemRecoveryRecord
    ) -> ProblemRecoveryRecord:
        self.ensure_layout()
        self._write_json(
            self.problems_dir / record.problem_id / "recovery.json",
            record.to_dict(),
        )
        return record

    def get_problem_recovery(self, problem_id: str) -> ProblemRecoveryRecord | None:
        data = self._read_json(self.problems_dir / problem_id / "recovery.json")
        if not data:
            return None
        return ProblemRecoveryRecord.from_dict(data)

    def list_problem_ids_for_execution(self, execution_id: str) -> list[str]:
        data = self._read_json(self.execution_problem_index_file) or {}
        mapping = data.get("execution_to_problems", {})
        problem_ids = mapping.get(execution_id, [])
        return problem_ids if isinstance(problem_ids, list) else []

    def list_problem_ids_for_case(self, case_id: str) -> list[str]:
        data = self._read_json(self.case_problem_index_file) or {}
        mapping = data.get("case_to_problems", {})
        problem_ids = mapping.get(case_id, [])
        return problem_ids if isinstance(problem_ids, list) else []

    def get_execution_artifact_index(self, execution_id: str) -> dict[str, Any] | None:
        self.ensure_layout()
        return self._read_json(
            self.artifacts_dir / execution_id / "indexes" / "artifact_index.json"
        )

    def get_execution_log_index(self, execution_id: str) -> dict[str, Any] | None:
        self.ensure_layout()
        return self._read_json(
            self.artifacts_dir / execution_id / "logs" / "log_index.json"
        )

    def read_artifact_file(self, relative_path: str | Path) -> Any:
        artifact_path = self.root_path / Path(relative_path)
        if not artifact_path.exists():
            return None
        if artifact_path.suffix == ".json":
            return self._read_json(artifact_path)
        return artifact_path.read_text(encoding="utf-8")

    def latest_executions_by_case(self) -> dict[str, ExecutionRecord]:
        latest: dict[str, ExecutionRecord] = {}
        for record in self.list_executions():
            latest[record.case_id] = record
        return latest

    def clear_executions(self) -> None:
        self.ensure_layout()
        if self.executions_dir.exists():
            shutil.rmtree(self.executions_dir)
        self.executions_dir.mkdir(parents=True, exist_ok=True)
        if self.artifacts_dir.exists():
            shutil.rmtree(self.artifacts_dir)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        if self.problems_dir.exists():
            shutil.rmtree(self.problems_dir)
        self.problems_dir.mkdir(parents=True, exist_ok=True)
        for path in (
            self.problems_index_file,
            self.execution_problem_index_file,
            self.case_problem_index_file,
        ):
            if path.exists():
                path.unlink()

    def clear_workspace_state(self) -> None:
        if self.objects_file.exists():
            self.objects_file.unlink()
        if self.tools_file.exists():
            self.tools_file.unlink()
        if self.environment_file.exists():
            self.environment_file.unlink()
        self.clear_executions()

    def _read_json(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write_json(self, path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)

    def _write_artifact_file(self, path: Path, data: Any) -> str:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False, default=str)
        return str(path.relative_to(self.root_path))

    def _list_workspace_logs(self) -> list[dict[str, Any]]:
        logs_dir = self.root_path / "logs"
        if not logs_dir.exists():
            return []

        entries: list[dict[str, Any]] = []
        for path in sorted(logs_dir.glob("*.log")):
            stat = path.stat()
            entries.append(
                {
                    "path": str(path.relative_to(self.root_path)),
                    "size": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                }
            )
        return entries

    def _relative_workspace_path(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.root_path))
        except ValueError:
            return str(path)

    def _link_problem_indexes(
        self, problem_id: str, execution_id: str, case_id: str
    ) -> None:
        if execution_id:
            execution_mapping = self._read_json(self.execution_problem_index_file) or {
                "execution_to_problems": {}
            }
            execution_mapping.setdefault("execution_to_problems", {})
            self._append_unique_mapping_value(
                execution_mapping["execution_to_problems"], execution_id, problem_id
            )
            self._write_json(self.execution_problem_index_file, execution_mapping)

        if case_id:
            case_mapping = self._read_json(self.case_problem_index_file) or {
                "case_to_problems": {}
            }
            case_mapping.setdefault("case_to_problems", {})
            self._append_unique_mapping_value(
                case_mapping["case_to_problems"], case_id, problem_id
            )
            self._write_json(self.case_problem_index_file, case_mapping)

    def _append_unique_mapping_value(
        self, mapping: dict[str, Any], key: str, value: str
    ) -> None:
        values = mapping.setdefault(key, [])
        if isinstance(values, list) and value not in values:
            values.append(value)
