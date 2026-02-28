# ptest/assertions/compat.py
# ptest 断言系统 - pytest/unittest 兼容层
#
# 提供与 pytest/unittest 兼容的断言接口

from __future__ import annotations

from typing import Any, Type, Literal

from .factory import AssertionFactory
from .result import AssertionResult


class AssertThat:
    """pytest 兼容的断言封装类

    使用方式:
        from ptest.assertions import assert_that

        assert_that(response.status_code).equals(200)
        assert_that(data).contains("key")
        assert_that(value).is_true()

    支持多种写法:
        assert_that(x).equals(y)   # 标准写法
        assert_that(x).eq(y)      # 简洁写法
    """

    def __init__(self, actual: Any):
        self.actual = actual
        self._last_result: AssertionResult | None = None

    def _execute(
        self, assertion_type: str, expected: Any = None, **kwargs
    ) -> AssertThat:
        """执行断言并抛出异常"""
        result = AssertionFactory.create(assertion_type).assert_value(
            self.actual, expected, **kwargs
        )
        self._last_result = result
        if not result.passed:
            raise AssertionError(result.get_error_message())
        return self

    # ============ 基础断言 ============

    def equals(self, expected: Any) -> AssertThat:
        """断言值相等"""
        return self._execute("equal", expected)

    def eq(self, expected: Any) -> AssertThat:
        """断言值相等 (equals 的简洁别名)"""
        return self.equals(expected)

    def not_equal(self, expected: Any) -> AssertThat:
        """断言值不相等"""
        return self._execute("notequal", expected)

    def not_equals(self, expected: Any) -> AssertThat:
        """断言值不相等 (not_equal 的别名)"""
        return self.not_equal(expected)

    def ne(self, expected: Any) -> AssertThat:
        """断言值不相等 (not_equal 的简洁别名)"""
        return self.not_equal(expected)

    def contains(self, expected: Any) -> AssertThat:
        """断言包含"""
        return self._execute("contains", expected)

    def is_in(self, item: Any) -> AssertThat:
        """断言 item 在 actual 中 (Python 习惯写法)"""
        return self._execute("contains", item)

    def in_(self, item: Any) -> AssertThat:
        """断言 item 在 actual 中 (is_in 的别名)"""
        return self.is_in(item)
        """断言 item 在 actual 中 (Python 习惯写法)"""
        return self._execute("contains", item)

    # ============ 真假值断言 ============

    def is_true(self) -> AssertThat:
        """断言值为真 (is_truthy 的改进)"""
        return self._execute("truthy")

    def is_truthy(self) -> AssertThat:
        """断言值为真"""
        return self.is_true()

    def true(self) -> AssertThat:
        """断言值为真 (is_true 的简洁别名)"""
        return self.is_true()

    def is_t(self) -> AssertThat:
        """断言值为真 (true 的极简别名)"""
        return self.is_true()

    def is_false(self) -> AssertThat:
        """断言值为假 (is_falsy 的改进)"""
        return self._execute("falsy")

    def is_falsy(self) -> AssertThat:
        """断言值为假"""
        return self.is_false()

    def false(self) -> AssertThat:
        """断言值为假 (is_false 的简洁别名)"""
        return self.is_false()

    def is_f(self) -> AssertThat:
        """断言值为假 (false 的极简别名)"""
        return self.is_false()

    # ============ None 断言 ============

    def is_none(self) -> AssertThat:
        """断言值为 None"""
        return self._execute("none")

    def not_none(self) -> AssertThat:
        """断言值不为 None (is_not_none 的改进)"""
        return self._execute("notnone")

    def is_not_none(self) -> AssertThat:
        """断言值不为 None"""
        return self.not_none()

    # ============ 类型断言 ============

    def is_instance(self, expected: Type | str) -> AssertThat:
        """断言类型 (is_type 的改进)"""
        return self._execute("type", expected)

    def is_type(self, expected: str) -> AssertThat:
        """断言类型"""
        return self.is_instance(expected)

    # ============ 长度断言 ============

    def len_is(self, expected: int, operator: str = "==") -> AssertThat:
        """断言长度 (has_length 的改进)"""
        return self._execute("length", expected, operator=operator)

    def has_length(self, expected: int, operator: str = "==") -> AssertThat:
        """断言长度"""
        return self.len_is(expected, operator)

    # ============ HTTP 断言 ============

    def status_code(self, expected: Any = None) -> AssertThat:
        """断言 HTTP 状态码"""
        return self._execute("statuscode", expected)

    def header(self, header_name: str, expected: Any = None) -> AssertThat:
        """断言 HTTP 响应头"""
        return self._execute("header", expected, header=header_name)

    def body(self, expected: Any = None) -> AssertThat:
        """断言 HTTP 响应体"""
        return self._execute("body", expected)

    def json_path(self, path: str, expected: Any = None) -> AssertThat:
        """断言 JSON 路径"""
        return self._execute("jsonpath", expected, path=path)

    # ============ 正则与 Schema ============

    def match(self, pattern: str) -> AssertThat:
        """正则匹配 (matches 的改进)"""
        return self._execute("regex", pattern)

    def matches(self, pattern: str) -> AssertThat:
        """正则匹配"""
        return self.match(pattern)

    def match_schema(self, schema: dict) -> AssertThat:
        """JSON Schema 验证 (conforms_to 的改进)"""
        return self._execute("schema", schema=schema)

    def conforms_to(self, schema: dict) -> AssertThat:
        """JSON Schema 验证"""
        return self.match_schema(schema)

    # ============ 便捷方法 ============

    @property
    def actual_value(self) -> Any:
        """获取实际值"""
        return self.actual

    def get_result(self) -> AssertionResult | None:
        """获取最后执行的断言结果"""
        return self._last_result


def assert_that(actual: Any) -> AssertThat:
    """创建断言

    使用方式:
        assert_that(response.status_code).equals(200)
        assert_that(data).contains("key")
        assert_that(value).is_true()

    Args:
        actual: 要断言的实际值

    Returns:
        AssertThat 实例
    """
    return AssertThat(actual)


# ============ 异常断言 ============


class AssertRaises:
    """异常断言上下文管理器

    使用方式:
        with assert_raises(ValueError) as ctx:
            raise ValueError("test error")
        assert "test error" in str(ctx.exception)
    """

    def __init__(self, expected_exception_type: Type[BaseException]):
        self.expected_exception_type = expected_exception_type
        self.actual_exception: BaseException | None = None
        self._entered = False

    def __enter__(self) -> AssertRaises:
        self._entered = True
        return self

    def __exit__(
        self,
        exc_type: Type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> Literal[True]:
        if exc_type is None:
            raise AssertionError(
                f"Expected {self.expected_exception_type.__name__} to be raised, "
                "but no exception was raised"
            )

        if not issubclass(exc_type, self.expected_exception_type):
            raise AssertionError(
                f"Expected {self.expected_exception_type.__name__}, "
                f"got {exc_type.__name__}: {exc_val}"
            )

        self.actual_exception = exc_val
        return True  # 抑制异常传播

    @property
    def exception(self) -> BaseException | None:
        """获取捕获的异常"""
        return self.actual_exception


def assert_raises(expected_exception_type: Type[BaseException]) -> AssertRaises:
    """创建异常断言上下文管理器

    Args:
        expected_exception_type: 期望的异常类型

    Returns:
        AssertRaises 实例
    """
    return AssertRaises(expected_exception_type)


# ============ 软断言 ============


class SoftAssertThat:
    """软断言的 assert_that 封装"""

    def __init__(self, soft_assertions: SoftAssertions, actual: Any):
        self.soft = soft_assertions
        self.actual = actual

    def _execute(
        self, assertion_type: str, expected: Any = None, **kwargs
    ) -> SoftAssertThat:
        """执行断言并收集结果"""
        result = AssertionFactory.create(assertion_type).assert_value(
            self.actual, expected, **kwargs
        )
        self.soft._add_result(result)
        return self

    # ============ 基础断言 ============

    def equals(self, expected: Any) -> SoftAssertThat:
        return self._execute("equal", expected)

    def eq(self, expected: Any) -> SoftAssertThat:
        return self.equals(expected)

    def not_equal(self, expected: Any) -> SoftAssertThat:
        return self._execute("notequal", expected)

    def not_equals(self, expected: Any) -> SoftAssertThat:
        return self.not_equal(expected)

    def ne(self, expected: Any) -> SoftAssertThat:
        return self.not_equal(expected)

    def contains(self, expected: Any) -> SoftAssertThat:
        return self._execute("contains", expected)

    def is_in(self, item: Any) -> SoftAssertThat:
        return self._execute("contains", item)

    def in_(self, item: Any) -> SoftAssertThat:
        return self.is_in(item)

    # ============ 真假值断言 ============
        return self._execute("contains", item)

    # ============ 真假值断言 ============

    def is_true(self) -> SoftAssertThat:
        return self._execute("truthy")

    def is_truthy(self) -> SoftAssertThat:
        return self.is_true()

    def true(self) -> SoftAssertThat:
        return self.is_true()

    def is_t(self) -> SoftAssertThat:
        return self.is_true()

    def is_false(self) -> SoftAssertThat:
        return self._execute("falsy")

    def is_falsy(self) -> SoftAssertThat:
        return self.is_false()

    def false(self) -> SoftAssertThat:
        return self.is_false()

    def is_f(self) -> SoftAssertThat:
        return self.is_false()

    # ============ None 断言 ============

    def is_none(self) -> SoftAssertThat:
        return self._execute("none")

    def not_none(self) -> SoftAssertThat:
        return self._execute("notnone")

    def is_not_none(self) -> SoftAssertThat:
        return self.not_none()

    # ============ 类型断言 ============

    def is_instance(self, expected: Type | str) -> SoftAssertThat:
        return self._execute("type", expected)

    def is_type(self, expected: str) -> SoftAssertThat:
        return self.is_instance(expected)

    # ============ 长度断言 ============

    def len_is(self, expected: int, operator: str = "==") -> SoftAssertThat:
        return self._execute("length", expected, operator=operator)

    def has_length(self, expected: int, operator: str = "==") -> SoftAssertThat:
        return self.len_is(expected, operator)

    # ============ HTTP 断言 ============

    def status_code(self, expected: Any = None) -> SoftAssertThat:
        return self._execute("statuscode", expected)

    # ============ 正则与 Schema ============

    def match(self, pattern: str) -> SoftAssertThat:
        return self._execute("regex", pattern)

    def matches(self, pattern: str) -> SoftAssertThat:
        return self.match(pattern)

    def match_schema(self, schema: dict) -> SoftAssertThat:
        return self._execute("schema", schema=schema)

    def conforms_to(self, schema: dict) -> SoftAssertThat:
        return self.match_schema(schema)


class SoftAssertions:
    """软断言上下文管理器 - 收集所有失败统一报告

    使用方式:
        with SoftAssertions() as soft:
            soft.assert_that(1).equals(2)
            soft.assert_that("a").equals("b")
        # 所有断言执行后才报告失败
    """

    def __init__(self):
        self.results: list[AssertionResult] = []

    def assert_that(self, actual: Any) -> SoftAssertThat:
        """创建软断言"""
        return SoftAssertThat(self, actual)

    def _add_result(self, result: AssertionResult) -> None:
        """添加断言结果"""
        self.results.append(result)

    def __enter__(self) -> SoftAssertions:
        return self

    def __exit__(
        self,
        exc_type: Type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> Literal[False]:
        if exc_type is not None:
            return False

        if self.results:
            failed = [r for r in self.results if not r.passed]
            if failed:
                messages = [r.get_error_message() for r in failed]
                raise AssertionError(
                    f"Soft assertion failures ({len(failed)}):\n"
                    + "\n".join(f"  - {m}" for m in messages)
                )
        return False


def soft_assertions() -> SoftAssertions:
    """创建软断言上下文管理器

    Returns:
        SoftAssertions 实例
    """
    return SoftAssertions()


# 导出公共 API
__all__ = [
    "assert_that",
    "assert_raises",
    "SoftAssertions",
    "soft_assertions",
    "AssertThat",
    "AssertRaises",
    "SoftAssertThat",
]
