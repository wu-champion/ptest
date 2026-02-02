# ptest/utils.py
import os
import sys
from pathlib import Path
from datetime import datetime
import json
from dataclasses import dataclass
from typing import Optional

from .core import get_logger

logger = get_logger("utils")


@dataclass
class CommandResult:
    """命令执行结果"""

    success: bool
    output: str
    error: Optional[str] = None

    def is_success(self) -> bool:
        return self.success

    def get_output(self) -> str:
        return self.output

    def get_error(self) -> Optional[str]:
        return self.error


def get_colored_text(text, color_code) -> str:
    """获取带颜色的文本"""
    return f"\033[{color_code}m{text}\033[0m"


def print_colored(text, color_code) -> None:
    """打印带颜色的文本"""
    print(get_colored_text(text, color_code))


def execute_command(cmd, timeout=30, cwd=None) -> CommandResult:
    """执行系统命令"""
    import subprocess

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd
        )
        if result.returncode == 0:
            return CommandResult(success=True, output=result.stdout)
        else:
            return CommandResult(
                success=False, output=result.stdout, error=result.stderr
            )
    except subprocess.TimeoutExpired:
        return CommandResult(
            success=False, output="", error=f"Command timed out after {timeout}s"
        )
    except Exception as e:
        return CommandResult(success=False, output="", error=str(e))
