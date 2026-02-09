# -*- coding: utf-8 -*-
"""ptest Fixtures模块 - 测试夹具管理

提供类似pytest的fixture机制，支持依赖注入和作用域管理。
"""

from __future__ import annotations

import functools
import inspect
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Generator

from ptest.core import get_logger

logger = get_logger("fixtures")


class FixtureScope(str, Enum):
    """Fixture作用域"""

    SESSION = "session"
    FUNCTION = "function"


@dataclass
class Fixture:
    """Fixture定义"""

    name: str
    scope: FixtureScope
    func: Callable[..., Any]
    _value: Any = None
    _initialized: bool = False

    def reset(self):
        """重置fixture状态"""
        self._value = None
        self._initialized = False


class FixtureManager:
    """Fixture管理器"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._fixtures: dict[str, Fixture] = {}
        self._session_values: dict[str, Any] = {}
        self._initialized = True

    def register(self, name: str, func: Callable[..., Any], scope: FixtureScope):
        """注册fixture"""
        self._fixtures[name] = Fixture(name=name, scope=scope, func=func)
        logger.debug(f"Registered fixture: {name} ({scope.value})")

    def get_or_create(self, name: str) -> Any:
        """获取或创建fixture值"""
        if name not in self._fixtures:
            raise ValueError(f"Fixture '{name}' not found")

        fixture = self._fixtures[name]

        if fixture.scope == FixtureScope.SESSION:
            if name not in self._session_values:
                self._session_values[name] = self._execute_fixture(fixture)
            return self._session_values[name]

        else:  # FUNCTION scope
            return self._execute_fixture(fixture)

    def _execute_fixture(self, fixture: Fixture) -> Any:
        """执行fixture函数"""
        result = fixture.func()

        # 支持generator（yield）
        if isinstance(result, Generator):
            try:
                value = next(result)
                return value
            except StopIteration:
                return None

        return result

    def cleanup_session(self):
        """清理session级别的fixtures"""
        self._session_values.clear()
        logger.debug("Cleaned up session fixtures")

    def cleanup_function(self):
        """清理function级别的fixtures"""
        # function级别的fixtures在每次使用时重新创建，无需清理
        pass

    def inject_fixtures(self, func: Callable[..., Any], **kwargs) -> dict[str, Any]:
        """为函数注入fixtures"""
        sig = inspect.signature(func)
        injected = {}

        for param_name in sig.parameters:
            if param_name in self._fixtures and param_name not in kwargs:
                injected[param_name] = self.get_or_create(param_name)

        return {**kwargs, **injected}


# 全局fixture管理器实例
_fixture_manager = FixtureManager()


def get_fixture_manager() -> FixtureManager:
    """获取全局fixture管理器"""
    return _fixture_manager


def fixture(scope: str = "function"):
    """Fixture装饰器

    使用示例:
        @fixture(scope="session")
        def database():
            db = create_test_database()
            yield db
            db.cleanup()

    Args:
        scope: Fixture作用域 (session/function)

    Returns:
        装饰器函数
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        scope_enum = FixtureScope(scope)
        manager = get_fixture_manager()
        manager.register(func.__name__, func, scope_enum)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return manager.get_or_create(func.__name__)

        return wrapper

    return decorator


def use_fixtures(*fixture_names: str):
    """使用fixtures装饰器

    为测试函数自动注入指定的fixtures。

    使用示例:
        @use_fixtures("database", "user_account")
        def test_user_profile(database, user_account):
            profile = database.get_profile(user_account.id)
            assert profile is not None

    Args:
        *fixture_names: 要注入的fixture名称

    Returns:
        装饰器函数
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            manager = get_fixture_manager()

            # 注入fixtures
            for name in fixture_names:
                if name not in kwargs:
                    kwargs[name] = manager.get_or_create(name)

            return func(*args, **kwargs)

        return wrapper

    return decorator
