from __future__ import annotations

from typing import Any

from .base import Assertion
from .result import AssertionResult


class AndAssertion(Assertion):
    """链式 AND 断言 - 所有断言都通过才通过"""

    def __init__(self, *assertions: Assertion, description: str = ""):
        super().__init__(description=description)
        self.assertions = assertions

    def assert_value(
        self, actual: Any, expected: Any = None, **kwargs: Any
    ) -> AssertionResult:
        results = []
        for assertion in self.assertions:
            result = assertion.assert_value(actual, expected, **kwargs)
            results.append(result)

        all_passed = all(r.passed for r in results)
        failed_results = [r for r in results if not r.passed]

        if all_passed:
            return self._create_result(True, actual, expected)
        else:
            return self._create_result(
                False,
                actual,
                expected,
                extra={
                    "chain_results": results,
                    "failed_count": len(failed_results),
                    "failed_messages": "; ".join(
                        r.get_error_message() for r in failed_results
                    ),
                },
            )

    def __repr__(self) -> str:
        return f"AndAssertion({len(self.assertions)} assertions)"


class OrAssertion(Assertion):
    """链式 OR 断言 - 任一断言通过就通过"""

    def __init__(self, *assertions: Assertion, description: str = ""):
        super().__init__(description=description)
        self.assertions = assertions

    def assert_value(
        self, actual: Any, expected: Any = None, **kwargs: Any
    ) -> AssertionResult:
        results = []
        for assertion in self.assertions:
            result = assertion.assert_value(actual, expected, **kwargs)
            results.append(result)

        any_passed = any(r.passed for r in results)
        passed_results = [r for r in results if r.passed]

        if any_passed:
            return self._create_result(
                True, actual, expected, extra={"passed_count": len(passed_results)}
            )
        else:
            return self._create_result(
                False, actual, expected, extra={"chain_results": results}
            )

    def __repr__(self) -> str:
        return f"OrAssertion({len(self.assertions)} assertions)"


class NotAssertion(Assertion):
    """链式 NOT 断言 - 断言失败才通过"""

    def __init__(self, assertion: Assertion, description: str = ""):
        super().__init__(description=description)
        self.assertion = assertion

    def assert_value(
        self, actual: Any, expected: Any = None, **kwargs: Any
    ) -> AssertionResult:
        result = self.assertion.assert_value(actual, expected, **kwargs)
        passed = not result.passed

        if passed:
            return self._create_result(True, actual, expected)
        else:
            return self._create_result(
                False, actual, expected, extra={"original_result": result.to_dict()}
            )

    def __repr__(self) -> str:
        return f"NotAssertion({self.assertion})"


class ChainBuilder:
    """链式断言构建器"""

    def __init__(self, initial_assertion: Assertion):
        self.assertions = [initial_assertion]

    def and_(self, assertion: Assertion) -> ChainBuilder:
        self.assertions.append(assertion)
        return self

    def or_(self, assertion: Assertion) -> ChainBuilder:
        combined = (
            OrAssertion(*self.assertions)
            if len(self.assertions) > 1
            else self.assertions[0]
        )
        return ChainBuilder(OrAssertion(combined, assertion))

    def not_(self) -> ChainBuilder:
        self.assertions = [NotAssertion(self.assertions[0])]
        return self

    def build(self) -> Assertion:
        if len(self.assertions) == 1:
            return self.assertions[0]
        return AndAssertion(*self.assertions)
