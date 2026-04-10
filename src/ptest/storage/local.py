from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LocalCliStateError(Exception):
    """Raised when the local CLI state file cannot be read safely."""

    state_path: Path
    reason: str

    def __str__(self) -> str:
        return f"{self.reason}: {self.state_path}"


class LocalCliStateStorage:
    """User-level CLI state storage for cross-workspace context."""

    def __init__(self, state_path: str | Path | None = None) -> None:
        self.state_path = (
            Path(state_path).expanduser().resolve()
            if state_path is not None
            else Path.home() / ".ptest" / "cli_state.json"
        )

    def read_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {}
        try:
            with open(self.state_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except json.JSONDecodeError as exc:
            raise LocalCliStateError(
                self.state_path,
                f"Invalid local CLI state JSON ({exc.msg})",
            ) from exc

        if not isinstance(data, dict):
            raise LocalCliStateError(
                self.state_path,
                "Local CLI state must be a JSON object",
            )
        return data

    def get_active_workspace(self) -> Path | None:
        state = self.read_state()
        value = state.get("active_workspace")
        if not isinstance(value, str) or not value.strip():
            return None
        return Path(value).expanduser().resolve()

    def set_active_workspace(self, workspace_path: str | Path) -> Path:
        path = Path(workspace_path).expanduser().resolve()
        payload = {
            "active_workspace": str(path),
            "updated_at": datetime.now().isoformat(),
        }
        self._write_state(payload)
        return path

    def clear_active_workspace(self) -> None:
        if self.state_path.exists():
            self.state_path.unlink()

    def _write_state(self, payload: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
