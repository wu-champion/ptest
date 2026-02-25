# ptest/assertions/registry.py
# ptest 断言注册模块
#
# 提供断言注册和管理功能

from __future__ import annotations

from typing import Type

from .base import Assertion


class AssertionRegistry:
    """断言注册表

    用于注册和管理自定义断言类型
    """

    _registry: dict[str, Type[Assertion]] = {}

    @classmethod
    def register(cls, name: str, assertion_class: Type[Assertion]) -> None:
        """注册断言类型

        Args:
            name: 断言类型名称
            assertion_class: 断言类
        """
        if not issubclass(assertion_class, Assertion):
            raise TypeError(f"{assertion_class} must be a subclass of Assertion")
        cls._registry[name] = assertion_class

    @classmethod
    def get(cls, name: str) -> Type[Assertion] | None:
        """获取断言类型

        Args:
            name: 断言类型名称

        Returns:
            断言类，如果不存在返回 None
        """
        return cls._registry.get(name)

    @classmethod
    def list_types(cls) -> list[str]:
        """列出所有已注册的断言类型

        Returns:
            断言类型名称列表
        """
        return list(cls._registry.keys())

    @classmethod
    def unregister(cls, name: str) -> bool:
        """注销断言类型

        Args:
            name: 断言类型名称

        Returns:
            是否成功注销
        """
        if name in cls._registry:
            del cls._registry[name]
            return True
        return False

    @classmethod
    def clear(cls) -> None:
        """清空所有注册的断言类型"""
        cls._registry.clear()

    @classmethod
    def is_registered(cls, name: str) -> bool:
        """检查断言类型是否已注册

        Args:
            name: 断言类型名称

        Returns:
            是否已注册
        """
        return name in cls._registry
