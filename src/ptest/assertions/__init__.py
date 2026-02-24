# ptest/assertions/__init__.py
# ptest 断言系统模块
#
# 提供内置断言功能，让用户无需依赖 pytest/unittest 即可完成测试
#
# 主要功能:
#   - 统一断言基类
#   - 断言结果标准化
#   - 断言工厂
#   - 内置断言类型 (status, json, header, body, regex, schema)

from .result import AssertionResult
from .base import Assertion
from .factory import AssertionFactory
from .registry import AssertionRegistry

__all__ = [
    "Assertion",
    "AssertionResult",
    "AssertionFactory",
    "AssertionRegistry",
]
