# ptest/assertions/result.py
# ptest 断言结果模块
#
# 定义断言执行结果的数据结构

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AssertionResult:
    """断言结果类

    用于存储单个断言的执行结果，包含成功状态、错误信息等
    """

    # 断言是否通过
    passed: bool = False

    # 断言类型
    assertion_type: str = ""

    # 期望值
    expected: Any = None

    # 实际值
    actual: Any = None

    # 错误信息
    message: str = ""

    # 断言描述
    description: str = ""

    # 自定义数据
    extra: dict[str, Any] = field(default_factory=dict)

    # 断言位置 - 文件路径
    file_path: str = ""

    # 断言位置 - 行号
    line_number: int = 0

    # 断言位置 - 函数名
    function_name: str = ""

    # 修复建议
    fix_suggestion: str = ""

    def is_passed(self) -> bool:
        """断言是否通过"""
        return self.passed

    def is_failed(self) -> bool:
        """断言是否失败"""
        return not self.passed

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "passed": self.passed,
            "assertion_type": self.assertion_type,
            "expected": self.expected,
            "actual": self.actual,
            "message": self.message,
            "description": self.description,
            "extra": self.extra,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "function_name": self.function_name,
            "fix_suggestion": self.fix_suggestion,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AssertionResult:
        """从字典创建"""
        return cls(
            passed=data.get("passed", False),
            assertion_type=data.get("assertion_type", ""),
            expected=data.get("expected"),
            actual=data.get("actual"),
            message=data.get("message", ""),
            description=data.get("description", ""),
            extra=data.get("extra", {}),
            file_path=data.get("file_path", ""),
            line_number=data.get("line_number", 0),
            function_name=data.get("function_name", ""),
            fix_suggestion=data.get("fix_suggestion", ""),
        )

    def get_error_message(self) -> str:
        """获取格式化的错误信息"""
        if self.passed:
            return ""

        parts = []

        # 添加描述
        if self.description:
            parts.append(f"断言失败: {self.description}")

        # 添加断言类型
        if self.assertion_type:
            parts.append(f"类型: {self.assertion_type}")

        # 添加期望值和实际值
        if self.expected is not None or self.actual is not None:
            parts.append(f"期望: {self.expected!r}")
            parts.append(f"实际: {self.actual!r}")

        # 添加自定义消息
        if self.message:
            parts.append(self.message)

        # 添加位置信息
        if self.file_path or self.line_number:
            location = self.file_path
            if self.line_number:
                location = (
                    f"{location}:{self.line_number}"
                    if location
                    else f"line {self.line_number}"
                )
            if self.function_name:
                location = f"{location} ({self.function_name})"
            parts.append(f"位置: {location}")

        # 添加修复建议
        if self.fix_suggestion:
            parts.append(f"建议: {self.fix_suggestion}")

        return " | ".join(parts)
