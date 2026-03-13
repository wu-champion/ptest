# ptest/assertions/factory.py
# ptest 断言工厂模块
#
# 提供断言创建和管理功能

from __future__ import annotations

from typing import Any, Type

from .base import Assertion
from .registry import AssertionRegistry


class AssertionFactory:
    """断言工厂

    用于创建断言实例
    """

    # 断言类型别名映射 (下划线格式 → 标准格式)
    ALIASES: dict[str, str] = {
        "status_code": "statuscode",
        "json_path": "jsonpath",
        "expected_exists": "exists",
        "body": "body",
        "header": "header",
        "regex": "regex",
        "schema": "schema",
    }

    @staticmethod
    def _resolve_type(assertion_type: str) -> str:
        """解析断言类型，支持别名映射"""
        from .builtins import BUILTIN_ASSERTIONS

        # 先尝试直接匹配
        if assertion_type in BUILTIN_ASSERTIONS:
            return assertion_type

        # 尝试别名映射
        if assertion_type in AssertionFactory.ALIASES:
            return AssertionFactory.ALIASES[assertion_type]

        # 尝试小写匹配
        lower_type = assertion_type.lower().replace("_", "")
        if lower_type in BUILTIN_ASSERTIONS:
            return lower_type

        return assertion_type

    @staticmethod
    def create(assertion_type: str, **kwargs: Any) -> Assertion:
        """创建断言实例

        Args:
            assertion_type: 断言类型
            **kwargs: 断言参数

        Returns:
            断言实例

        Raises:
            ValueError: 如果断言类型不存在
        """
        # 解析类型（支持别名）
        resolved_type = AssertionFactory._resolve_type(assertion_type)

        # 尝试从注册表获取
        assertion_class = AssertionRegistry.get(resolved_type)
        if assertion_class is not None:
            return assertion_class(**kwargs)

        # 尝试从内置断言获取
        from .builtins import BUILTIN_ASSERTIONS

        if resolved_type in BUILTIN_ASSERTIONS:
            return BUILTIN_ASSERTIONS[resolved_type](**kwargs)

        raise ValueError(f"Unknown assertion type: {assertion_type}")

    @staticmethod
    def list_available() -> list[str]:
        """列出所有可用的断言类型

        Returns:
            断言类型列表
        """
        from .builtins import BUILTIN_ASSERTIONS

        return list(BUILTIN_ASSERTIONS.keys()) + AssertionRegistry.list_types()

    @staticmethod
    def register_custom(name: str, assertion_class: Type[Assertion]) -> None:
        """注册自定义断言

        Args:
            name: 断言类型名称
            assertion_class: 断言类
        """
        AssertionRegistry.register(name, assertion_class)
