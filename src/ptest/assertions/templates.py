from __future__ import annotations

from typing import Any, Callable, Dict

from .base import Assertion
from .result import AssertionResult


class TemplateAssertion(Assertion):
    """模板断言 - 支持参数化的可重用断言"""

    def __init__(
        self,
        template_fn: Callable[..., AssertionResult],
        params: Dict[str, Any],
        description: str = "",
    ):
        super().__init__(description=description)
        self.template_fn = template_fn
        self.params = params

    def assert_value(
        self, actual: Any, expected: Any = None, **kwargs: Any
    ) -> AssertionResult:
        merged_params = {**self.params, **kwargs}
        return self.template_fn(actual, expected, **merged_params)

    def __repr__(self) -> str:
        return f"TemplateAssertion(params={self.params})"


class AssertionTemplate:
    """断言模板管理器"""

    _templates: Dict[str, Callable[..., AssertionResult]] = {}

    @classmethod
    def register(
        cls,
        name: str,
        template_fn: Callable[..., AssertionResult],
    ) -> None:
        cls._templates[name] = template_fn

    @classmethod
    def get(cls, name: str) -> Callable[..., AssertionResult] | None:
        return cls._templates.get(name)

    @classmethod
    def list_templates(cls) -> list[str]:
        return list(cls._templates.keys())

    @classmethod
    def unregister(cls, name: str) -> bool:
        if name in cls._templates:
            del cls._templates[name]
            return True
        return False

    @classmethod
    def create(
        cls, name: str, params: Dict[str, Any] | None = None, description: str = ""
    ) -> Assertion:
        template_fn = cls.get(name)
        if template_fn is None:
            raise ValueError(f"Template '{name}' not found")
        return TemplateAssertion(template_fn, params or {}, description=description)


def http_response_template(
    actual: Any, expected: Any = None, **kwargs: Any
) -> AssertionResult:
    """HTTP 响应断言模板"""
    from .factory import AssertionFactory

    checks = kwargs.get("checks", ["status", "body"])
    results = []

    if "status" in checks:
        status_assert = AssertionFactory.create("statuscode")
        results.append(
            status_assert.assert_value(
                actual.get("status_code", 0),
                expected.get("status_code", 200) if isinstance(expected, dict) else 200,
            )
        )

    if "body" in checks:
        body_assert = AssertionFactory.create("body")
        results.append(
            body_assert.assert_value(
                actual.get("body"),
                expected.get("body") if isinstance(expected, dict) else None,
            )
        )

    all_passed = all(r.passed for r in results)
    return AssertionResult(
        passed=all_passed,
        actual=actual,
        expected=expected,
        assertion_type="HttpResponseTemplate",
    )


def api_success_template(
    actual: Any, expected: Any = None, **kwargs: bool
) -> AssertionResult:
    """API 成功响应断言模板"""
    from .factory import AssertionFactory

    code_assert = AssertionFactory.create("statuscode")
    code_result = code_assert.assert_value(
        actual.get("code", -1),
        expected.get("code", 0) if isinstance(expected, dict) else 0,
    )

    msg_assert = AssertionFactory.create("truthy")
    msg_result = msg_assert.assert_value(actual.get("message", ""))

    return AssertionResult(
        passed=code_result.passed and msg_result.passed,
        actual=actual,
        expected=expected,
        assertion_type="ApiSuccessTemplate",
    )


AssertionTemplate.register("http_response", http_response_template)
AssertionTemplate.register("api_success", api_success_template)
