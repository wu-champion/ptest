# ptest/assertions/base.py
# ptest 断言基类模块
#
# 定义断言的抽象基类

from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from typing import Any

from .result import AssertionResult

# 修复建议映射
FIX_SUGGESTIONS: dict[str, str] = {
    "EqualAssertion": "检查比较的值是否正确，可能需要调整期望值或实际值",
    "NotEqualAssertion": "检查是否应该使用相等断言",
    "ContainsAssertion": "检查目标字符串/列表是否包含期望的内容",
    "StatusCodeAssertion": "检查HTTP响应状态码是否符合预期",
    "JsonPathAssertion": "检查JSON路径是否正确，验证路径是否存在",
    "HeaderAssertion": "检查响应头是否包含所需的header",
    "BodyAssertion": "检查响应体内容是否匹配",
    "RegexAssertion": "检查正则表达式是否正确匹配目标",
    "SchemaAssertion": "检查JSON结构是否符合schema定义",
    "LengthAssertion": "检查集合/字符串长度是否满足条件",
    "TypeAssertion": "检查值的类型是否正确",
    "TruthyAssertion": "检查值是否为真值 (非零、非空、非None)",
    "FalsyAssertion": "检查值是否为假值 (零、空、None)",
    "NoneAssertion": "检查值是否为空 (None)",
    "NotNoneAssertion": "检查值是否非空",
}


class Assertion(ABC):
    """断言基类

    所有断言类型都继承自此类，实现 assert_value 方法
    """

    def __init__(self, description: str = "", message: str = ""):
        """初始化断言

        Args:
            description: 断言描述
            message: 自定义错误消息
        """
        self.description = description
        self.message = message

    @abstractmethod
    def assert_value(
        self, actual: Any, expected: Any = None, **kwargs: Any
    ) -> AssertionResult:
        """执行断言

        Args:
            actual: 实际值
            expected: 期望值 (可选)
            **kwargs: 其他参数

        Returns:
            断言结果
        """
        pass

    def _create_result(
        self,
        passed: bool,
        actual: Any,
        expected: Any = None,
        extra: dict[str, Any] | None = None,
        capture_location: bool = False,
    ) -> AssertionResult:
        """创建断言结果

        Args:
            passed: 是否通过
            actual: 实际值
            expected: 期望值
            extra: 额外数据
            capture_location: 是否捕获调用位置（默认关闭以提升性能）

        Returns:
            断言结果
        """
        # 捕获调用位置（可选，默认关闭以提升性能）
        file_path = ""
        line_number = 0
        function_name = ""

        if capture_location:
            frame = inspect.currentframe()
            caller_frame = None

            if frame is not None:
                for f in inspect.getouterframes(frame):
                    if f.function not in ("_create_result", "assert_value", "__init__"):
                        caller_frame = f
                        break

            if caller_frame is not None:
                file_path = caller_frame.filename
                line_number = caller_frame.lineno
                function_name = caller_frame.function

        # 获取修复建议
        assertion_type = self.__class__.__name__
        fix_suggestion = FIX_SUGGESTIONS.get(assertion_type, "检查断言逻辑是否正确")

        result = AssertionResult(
            passed=passed,
            assertion_type=assertion_type,
            expected=expected,
            actual=actual,
            description=self.description,
            message=self.message,
            extra=extra or {},
            file_path=file_path,
            line_number=line_number,
            function_name=function_name,
            fix_suggestion=fix_suggestion,
        )
        return result

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(description={self.description!r})"
