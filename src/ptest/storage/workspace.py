from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from ..models import (
    EnvironmentRecord,
    ExecutionRecord,
    ManagedObjectRecord,
    ToolRecord,
)


class WorkspaceStorage:
    """File-backed storage for the first-phase workflow."""

    def __init__(self, root_path: Path):
        self.root_path = Path(root_path).resolve()
        self.meta_dir = self.root_path / ".ptest"
        self.executions_dir = self.meta_dir / "executions"
        self.artifacts_dir = self.meta_dir / "artifacts"
        self.environment_file = self.meta_dir / "environment.json"
        self.objects_file = self.meta_dir / "objects.json"
        self.tools_file = self.meta_dir / "tools.json"

    def ensure_layout(self) -> None:
        self.meta_dir.mkdir(parents=True, exist_ok=True)
        self.executions_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

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
            item["name"]: ToolRecord.from_dict(item)
            for item in data.get("tools", [])
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

        files = {
            "environment": self._write_artifact_file(
                artifact_dir / "environment.json",
                environment,
            ),
            "objects": self._write_artifact_file(
                artifact_dir / "objects.json",
                {"objects": objects},
            ),
            "case": self._write_artifact_file(
                artifact_dir / "case.json",
                case or {},
            ),
            "result": self._write_artifact_file(
                artifact_dir / "result.json",
                result,
            ),
        }

        if output not in (None, ""):
            output_path = artifact_dir / (
                "output.txt" if isinstance(output, str) else "output.json"
            )
            if isinstance(output, str):
                output_path.write_text(output, encoding="utf-8")
                files["output"] = str(output_path.relative_to(self.root_path))
            else:
                files["output"] = self._write_artifact_file(output_path, output)

        return {
            "directory": str(artifact_dir.relative_to(self.root_path)),
            "files": files,
        }

    def save_execution_artifact_record(self, record: ExecutionRecord) -> str:
        self.ensure_layout()
        artifact_dir = self.artifacts_dir / record.execution_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        return self._write_artifact_file(
            artifact_dir / "execution.json",
            record.to_dict(),
        )

    def list_executions(self) -> list[ExecutionRecord]:
        self.ensure_layout()
        records: list[ExecutionRecord] = []
        for path in sorted(self.executions_dir.glob("*.json")):
            data = self._read_json(path)
            if data:
                records.append(ExecutionRecord.from_dict(data))
        return records

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
