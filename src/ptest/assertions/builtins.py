# ptest/assertions/builtins.py
# ptest 内置断言模块
#
# 提供所有内置断言类型实现

from __future__ import annotations

import json
import re
from typing import Any

from .base import Assertion
from .result import AssertionResult


# 断言类型映射
BUILTIN_ASSERTIONS: dict[str, type[Assertion]] = {}


def _register_assertion(cls: type[Assertion]) -> type[Assertion]:
    """注册断言类到内置映射"""
    BUILTIN_ASSERTIONS[cls.__name__.replace("Assertion", "").lower()] = cls
    return cls


@_register_assertion
class StatusCodeAssertion(Assertion):
    """HTTP 状态码断言"""

    def assert_value(
        self, actual: Any, expected: Any = None, **kwargs: Any
    ) -> AssertionResult:
        try:
            actual_code = int(actual)
        except (ValueError, TypeError):
            return self._create_result(
                passed=False,
                actual=actual,
                expected=expected,
                extra={"error": f"Invalid status code: {actual!r}"},
            )

        try:
            expected_codes = (
                set(expected) if isinstance(expected, (list, tuple)) else {expected}
            )
        except (ValueError, TypeError):
            expected_codes = {expected}

        passed = actual_code in expected_codes
        return self._create_result(
            passed=passed,
            actual=actual_code,
            expected=expected_codes,
        )


@_register_assertion
class JsonPathAssertion(Assertion):
    """JSON 路径断言"""

    def assert_value(
        self, actual: Any, expected: Any = None, **kwargs: Any
    ) -> AssertionResult:
        path = kwargs.get("path", "")

        # 尝试解析 JSON
        if isinstance(actual, str):
            try:
                actual = json.loads(actual)
            except json.JSONDecodeError:
                return self._create_result(
                    passed=False,
                    actual=actual,
                    expected=expected,
                    extra={"error": "Invalid JSON string"},
                )

        # 简单 JSON 路径解析
        try:
            value = self._get_json_path(actual, path)
        except Exception as e:
            return self._create_result(
                passed=False,
                actual=actual,
                expected=expected,
                extra={"error": str(e)},
            )

        passed = value == expected
        return self._create_result(
            passed=passed,
            actual=value,
            expected=expected,
            extra={"path": path},
        )

    def _get_json_path(self, data: Any, path: str) -> Any:
        """获取 JSON 路径对应的值"""
        if not path:
            return data

        parts = path.replace("$.", "").split(".")
        current = data

        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list):
                try:
                    index = int(part)
                    current = current[index]
                except (ValueError, IndexError):
                    raise ValueError(f"Invalid path: {part}")
            else:
                raise ValueError(f"Cannot navigate through: {type(current)}")

        return current


@_register_assertion
class HeaderAssertion(Assertion):
    """HTTP 响应头断言"""

    def assert_value(
        self, actual: Any, expected: Any = None, **kwargs: Any
    ) -> AssertionResult:
        header_name = kwargs.get("header", "")

        if not isinstance(actual, dict):
            return self._create_result(
                passed=False,
                actual=actual,
                expected=expected,
                extra={"error": "Headers must be a dictionary"},
            )

        # Normalize headers to lowercase keys for case-insensitive lookup
        normalized_headers = {k.lower(): v for k, v in actual.items()}
        header_key = header_name.lower()

        if expected is None:
            passed = header_key in normalized_headers
        else:
            actual_value = normalized_headers.get(header_key)
            passed = actual_value == expected

        return self._create_result(
            passed=passed,
            actual=normalized_headers.get(header_key),
            expected=expected,
            extra={"header": header_name},
        )


@_register_assertion
class BodyAssertion(Assertion):
    """响应体断言"""

    def assert_value(
        self, actual: Any, expected: Any = None, **kwargs: Any
    ) -> AssertionResult:
        # 如果期望是字符串，尝试解析为 JSON
        if isinstance(expected, str):
            try:
                expected = json.loads(expected)
            except json.JSONDecodeError:
                pass

        # 如果实际是字符串，尝试解析为 JSON
        if isinstance(actual, str):
            try:
                actual = json.loads(actual)
            except json.JSONDecodeError:
                pass

        passed = actual == expected
        return self._create_result(
            passed=passed,
            actual=actual,
            expected=expected,
        )


@_register_assertion
class RegexAssertion(Assertion):
    """正则表达式断言"""

    def assert_value(
        self, actual: Any, expected: Any = None, **kwargs: Any
    ) -> AssertionResult:
        if not isinstance(actual, str):
            actual = str(actual)

        if expected is None:
            return self._create_result(
                passed=False,
                actual=actual,
                expected=expected,
                extra={"error": "Pattern is required"},
            )

        try:
            pattern = re.compile(expected)
            match = pattern.search(actual)
            passed = match is not None
        except re.error as e:
            return self._create_result(
                passed=False,
                actual=actual,
                expected=expected,
                extra={"error": f"Invalid regex: {e}"},
            )

        return self._create_result(
            passed=passed,
            actual=actual,
            expected=expected,
            extra={"match": match.group() if match else None},
        )


@_register_assertion
class SchemaAssertion(Assertion):
    """JSON Schema 断言"""

    def assert_value(
        self, actual: Any, expected: Any = None, **kwargs: Any
    ) -> AssertionResult:
        schema = kwargs.get("schema")

        if schema is None:
            return self._create_result(
                passed=False,
                actual=actual,
                expected=expected,
                extra={"error": "Schema is required"},
            )

        # 简单 schema 验证
        try:
            passed = self._validate_schema(actual, schema)
        except Exception as e:
            return self._create_result(
                passed=False,
                actual=actual,
                expected=expected,
                extra={"error": str(e)},
            )

        return self._create_result(
            passed=passed,
            actual=type(actual).__name__,
            expected="schema",
            extra={"schema": schema},
        )

    def _validate_schema(self, data: Any, schema: dict[str, Any]) -> bool:
        """简单 schema 验证"""
        # 基础类型验证
        if "type" in schema:
            expected_type = schema["type"]

            type_map = {
                "string": str,
                "number": (int, float),
                "integer": int,
                "boolean": bool,
                "array": list,
                "object": dict,
                "null": type(None),
            }

            if expected_type in type_map:
                expected_class = type_map[expected_type]
                if not isinstance(data, expected_class):  # type: ignore[arg-type]
                    return False

        # 属性验证
        if "properties" in schema and isinstance(data, dict):
            for prop, prop_schema in schema["properties"].items():
                if prop in data:
                    if not self._validate_schema(data[prop], prop_schema):
                        return False

        # 必填验证
        if "required" in schema and isinstance(data, dict):
            for required_prop in schema["required"]:
                if required_prop not in data:
                    return False

        return True


@_register_assertion
class EqualAssertion(Assertion):
    """相等断言"""

    def assert_value(
        self, actual: Any, expected: Any = None, **kwargs: Any
    ) -> AssertionResult:
        passed = actual == expected
        return self._create_result(
            passed=passed,
            actual=actual,
            expected=expected,
        )


@_register_assertion
class NotEqualAssertion(Assertion):
    """不相等断言"""

    def assert_value(
        self, actual: Any, expected: Any = None, **kwargs: Any
    ) -> AssertionResult:
        passed = actual != expected
        return self._create_result(
            passed=passed,
            actual=actual,
            expected=expected,
        )


@_register_assertion
class ContainsAssertion(Assertion):
    """包含断言"""

    def assert_value(
        self, actual: Any, expected: Any = None, **kwargs: Any
    ) -> AssertionResult:
        try:
            passed = expected in actual
        except TypeError:
            return self._create_result(
                passed=False,
                actual=actual,
                expected=expected,
                extra={"error": "Cannot check containment"},
            )

        return self._create_result(
            passed=passed,
            actual=actual,
            expected=expected,
        )


@_register_assertion
class LengthAssertion(Assertion):
    """长度断言"""

    def assert_value(
        self, actual: Any, expected: Any = None, **kwargs: Any
    ) -> AssertionResult:
        try:
            actual_length = len(actual)
        except TypeError:
            return self._create_result(
                passed=False,
                actual=actual,
                expected=expected,
                extra={"error": "Cannot get length"},
            )

        operator = kwargs.get("operator", "==")

        if operator == "==":
            passed = actual_length == expected
        elif operator == ">":
            passed = actual_length > expected
        elif operator == ">=":
            passed = actual_length >= expected
        elif operator == "<":
            passed = actual_length < expected
        elif operator == "<=":
            passed = actual_length <= expected
        else:
            passed = False

        return self._create_result(
            passed=passed,
            actual=actual_length,
            expected=expected,
            extra={"operator": operator},
        )


@_register_assertion
class TypeAssertion(Assertion):
    """类型断言"""

    def assert_value(
        self, actual: Any, expected: Any = None, **kwargs: Any
    ) -> AssertionResult:
        if expected is None:
            return self._create_result(
                passed=False,
                actual=type(actual).__name__,
                expected=expected,
                extra={"error": "Type name is required"},
            )

        type_map = {
            "str": str,
            "string": str,
            "int": int,
            "integer": int,
            "float": float,
            "bool": bool,
            "boolean": bool,
            "list": list,
            "dict": dict,
            "object": dict,
            "none": type(None),
            "null": type(None),
        }

        expected_class = type_map.get(str(expected).lower())
        if expected_class is None:
            return self._create_result(
                passed=False,
                actual=type(actual).__name__,
                expected=expected,
                extra={"error": f"Unknown type: {expected}"},
            )

        passed = isinstance(actual, expected_class)
        return self._create_result(
            passed=passed,
            actual=type(actual).__name__,
            expected=expected,
        )


@_register_assertion
class TruthyAssertion(Assertion):
    """真值断言"""

    def assert_value(
        self, actual: Any, expected: Any = None, **kwargs: Any
    ) -> AssertionResult:
        passed = bool(actual)
        return self._create_result(
            passed=passed,
            actual=actual,
            expected="truthy",
        )


@_register_assertion
class FalsyAssertion(Assertion):
    """假值断言"""

    def assert_value(
        self, actual: Any, expected: Any = None, **kwargs: Any
    ) -> AssertionResult:
        passed = not bool(actual)
        return self._create_result(
            passed=passed,
            actual=actual,
            expected="falsy",
        )


@_register_assertion
class NoneAssertion(Assertion):
    """空值断言"""

    def assert_value(
        self, actual: Any, expected: Any = None, **kwargs: Any
    ) -> AssertionResult:
        is_none = actual is None
        return self._create_result(
            passed=is_none,
            actual=actual,
            expected=None,
        )


@_register_assertion
class NotNoneAssertion(Assertion):
    """非空值断言"""

    def assert_value(
        self, actual: Any, expected: Any = None, **kwargs: Any
    ) -> AssertionResult:
        is_not_none = actual is not None
        return self._create_result(
            passed=is_not_none,
            actual=actual,
            expected="not_none",
        )
