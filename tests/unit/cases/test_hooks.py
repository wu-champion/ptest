# -*- coding: utf-8 -*-
"""Hooks系统单元测试 / Hooks System Unit Tests"""

import pytest
from unittest.mock import Mock, patch

from ptest.cases.hooks import (
    Hook,
    HookActionType,
    HookExecutor,
    HookManager,
    HookResult,
    HookType,
)


class TestHookEnums:
    """Hook枚举测试"""

    def test_hook_type_values(self):
        """测试Hook类型值"""
        assert HookType.SETUP.value == "setup"
        assert HookType.TEARDOWN.value == "teardown"

    def test_hook_action_type_values(self):
        """测试Hook动作类型值"""
        assert HookActionType.COMMAND.value == "command"
        assert HookActionType.API.value == "api"
        assert HookActionType.SQL.value == "sql"
        assert HookActionType.FUNCTION.value == "function"


class TestHook:
    """Hook数据类测试"""

    def test_hook_creation(self):
        """测试Hook创建"""
        hook = Hook(
            name="setup_hook",
            hook_type=HookType.SETUP,
            action_type=HookActionType.COMMAND,
            action_params={"command": "echo test"},
        )

        assert hook.name == "setup_hook"
        assert hook.hook_type == HookType.SETUP
        assert hook.action_type == HookActionType.COMMAND
        assert hook.action_params["command"] == "echo test"

    def test_hook_optional_fields(self):
        """测试Hook可选字段"""
        hook = Hook(
            name="simple_hook",
            hook_type=HookType.TEARDOWN,
            action_type=HookActionType.COMMAND,
            action_params={},
        )

        assert hook.condition is None
        assert hook.timeout == 300
        assert hook.ignore_failure is False

    def test_hook_with_condition(self):
        """测试带条件的Hook"""
        hook = Hook(
            name="conditional_hook",
            hook_type=HookType.SETUP,
            action_type=HookActionType.API,
            action_params={"url": "http://test"},
            condition="only_on_success",
        )

        assert hook.condition == "only_on_success"


class TestHookResult:
    """HookResult测试"""

    def test_hook_result_success(self):
        """测试成功结果"""
        result = HookResult(
            hook_name="test_hook",
            success=True,
            output="success output",
        )

        assert result.hook_name == "test_hook"
        assert result.success is True
        assert result.output == "success output"
        assert result.error is None

    def test_hook_result_failure(self):
        """测试失败结果"""
        result = HookResult(
            hook_name="test_hook",
            success=False,
            error="Something went wrong",
        )

        assert result.success is False
        assert result.error == "Something went wrong"


class TestHookExecutor:
    """HookExecutor测试"""

    def test_executor_creation(self):
        """测试执行器创建"""
        executor = HookExecutor()
        assert executor is not None

    def test_execute_command_hook(self):
        """测试执行命令Hook"""
        executor = HookExecutor()
        hook = Hook(
            name="cmd_hook",
            hook_type=HookType.SETUP,
            action_type=HookActionType.COMMAND,
            action_params={"command": "echo hello"},
        )

        result = executor.execute(hook)
        assert result.hook_name == "cmd_hook"
        assert result.success is True

    def test_execute_api_hook(self):
        """测试执行API Hook"""
        executor = HookExecutor()
        hook = Hook(
            name="api_hook",
            hook_type=HookType.SETUP,
            action_type=HookActionType.API,
            action_params={
                "method": "GET",
                "url": "http://example.com",
            },
        )

        with patch("requests.request") as mock_request:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_request.return_value = mock_response

            result = executor.execute(hook)
            assert result.hook_name == "api_hook"
            mock_request.assert_called_once()

    def test_execute_sql_hook(self):
        """测试执行SQL Hook"""
        executor = HookExecutor()
        hook = Hook(
            name="sql_hook",
            hook_type=HookType.SETUP,
            action_type=HookActionType.SQL,
            action_params={
                "connection_string": "sqlite:///test.db",
                "query": "SELECT 1",
            },
        )

        with patch("sqlite3.connect") as mock_connect:
            mock_cursor = Mock()
            mock_cursor.fetchall.return_value = [(1,)]
            mock_connect.return_value.cursor.return_value = mock_cursor

            result = executor.execute(hook)
            assert result.hook_name == "sql_hook"
            mock_connect.assert_called_once()

    def test_execute_function_hook(self):
        """测试执行函数Hook"""
        executor = HookExecutor()

        test_func = Mock(return_value="function result")
        hook = Hook(
            name="func_hook",
            hook_type=HookType.SETUP,
            action_type=HookActionType.FUNCTION,
            action_params={"function": test_func, "args": [], "kwargs": {}},
        )

        result = executor.execute(hook)
        assert result.hook_name == "func_hook"
        test_func.assert_called_once()

    def test_execute_hook_timeout(self):
        """测试Hook超时"""
        executor = HookExecutor()
        hook = Hook(
            name="slow_hook",
            hook_type=HookType.SETUP,
            action_type=HookActionType.COMMAND,
            action_params={"command": "sleep 10"},
            timeout=0.1,
        )

        result = executor.execute(hook)
        assert result.success is False
        assert "timeout" in result.error.lower()


class TestHookManager:
    """HookManager测试"""

    def test_manager_creation(self):
        """测试管理器创建"""
        manager = HookManager()
        assert manager is not None

    def test_register_hook(self):
        """测试注册Hook"""
        manager = HookManager()
        hook = Hook(
            name="test_hook",
            hook_type=HookType.SETUP,
            action_type=HookActionType.COMMAND,
            action_params={"command": "echo test"},
        )

        manager.register(hook)
        assert "test_hook" in manager.hooks

    def test_unregister_hook(self):
        """测试注销Hook"""
        manager = HookManager()
        hook = Hook(
            name="removable_hook",
            hook_type=HookType.SETUP,
            action_type=HookActionType.COMMAND,
            action_params={},
        )

        manager.register(hook)
        manager.unregister("removable_hook")
        assert "removable_hook" not in manager.hooks

    def test_get_hooks_by_type(self):
        """测试按类型获取Hooks"""
        manager = HookManager()

        setup_hook = Hook(
            name="setup",
            hook_type=HookType.SETUP,
            action_type=HookActionType.COMMAND,
            action_params={},
        )
        teardown_hook = Hook(
            name="teardown",
            hook_type=HookType.TEARDOWN,
            action_type=HookActionType.COMMAND,
            action_params={},
        )

        manager.register(setup_hook)
        manager.register(teardown_hook)

        setup_hooks = manager.get_hooks_by_type(HookType.SETUP)
        assert len(setup_hooks) == 1
        assert setup_hooks[0].name == "setup"

    def test_execute_hooks(self):
        """测试批量执行Hooks"""
        manager = HookManager()
        executor = HookExecutor()

        hook1 = Hook(
            name="hook1",
            hook_type=HookType.SETUP,
            action_type=HookActionType.COMMAND,
            action_params={"command": "echo 1"},
        )
        hook2 = Hook(
            name="hook2",
            hook_type=HookType.SETUP,
            action_type=HookActionType.COMMAND,
            action_params={"command": "echo 2"},
        )

        manager.register(hook1)
        manager.register(hook2)

        results = manager.execute_hooks(HookType.SETUP, executor)
        assert len(results) == 2
        assert all(r.success for r in results)

    def test_execute_hooks_stop_on_failure(self):
        """测试失败时停止"""
        manager = HookManager()
        executor = HookExecutor()

        hook1 = Hook(
            name="success_hook",
            hook_type=HookType.SETUP,
            action_type=HookActionType.COMMAND,
            action_params={"command": "echo success"},
        )
        hook2 = Hook(
            name="fail_hook",
            hook_type=HookType.SETUP,
            action_type=HookActionType.COMMAND,
            action_params={"command": "exit 1"},
            ignore_failure=False,
        )

        manager.register(hook1)
        manager.register(hook2)

        results = manager.execute_hooks(HookType.SETUP, executor, stop_on_failure=True)
        # 应该执行到失败为止
        assert any(not r.success for r in results)
