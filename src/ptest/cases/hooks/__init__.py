"""ptest 测试用例 hooks 模块 - Setup/Teardown 支持"""

from __future__ import annotations

import sqlite3
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ...core import get_logger

logger = get_logger("cases.hooks")


class HookType(str, Enum):
    """Hook 类型"""

    COMMAND = "command"
    API = "api"
    SQL = "sql"
    FUNCTION = "function"


class HookWhen(str, Enum):
    """Hook 执行时机"""

    SETUP = "setup"
    TEARDOWN = "teardown"


@dataclass
class HookResult:
    """Hook 执行结果"""

    success: bool
    output: str = ""
    error: str = ""
    duration: float = 0.0


@dataclass
class Hook:
    """Hook 定义"""

    type: HookType
    when: HookWhen
    config: dict[str, Any] = field(default_factory=dict)
    only_on_success: bool = False
    always_run: bool = True
    name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "when": self.when.value,
            "config": self.config,
            "only_on_success": self.only_on_success,
            "always_run": self.always_run,
            "name": self.name,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Hook:
        return cls(
            type=HookType(data.get("type", "command")),
            when=HookWhen(data.get("when", "setup")),
            config=data.get("config", {}),
            only_on_success=data.get("only_on_success", False),
            always_run=data.get("always_run", True),
            name=data.get("name", ""),
        )


class HookExecutor:
    """Hook 执行器"""

    def __init__(self, env_manager):
        self.env_manager = env_manager

    def execute_hook(
        self, hook: Hook, context: dict[str, Any] | None = None
    ) -> HookResult:
        """
        执行单个 hook

        Args:
            hook: Hook 定义
            context: 执行上下文（包含测试数据、变量等）

        Returns:
            HookResult: 执行结果
        """
        logger.info(f"Executing {hook.when.value} hook: {hook.name or hook.type.value}")

        try:
            if hook.type == HookType.COMMAND:
                return self._execute_command(hook, context)
            elif hook.type == HookType.API:
                return self._execute_api(hook, context)
            elif hook.type == HookType.SQL:
                return self._execute_sql(hook, context)
            elif hook.type == HookType.FUNCTION:
                return self._execute_function(hook, context)
            else:
                return HookResult(
                    success=False, error=f"Unknown hook type: {hook.type}"
                )
        except Exception as e:
            logger.error(f"Hook execution failed: {e}")
            return HookResult(success=False, error=str(e))

    def _execute_command(
        self, hook: Hook, context: dict[str, Any] | None
    ) -> HookResult:
        """执行命令类型 hook"""
        command = hook.config.get("command", "")
        if not command:
            return HookResult(success=False, error="Command not specified")

        cwd = hook.config.get("cwd")
        timeout = hook.config.get("timeout", 60)
        use_shell = hook.config.get("use_shell", True)

        if use_shell:
            logger.warning(
                f"Executing command with shell=True: {command}. "
                "This may have security implications."
            )

        try:
            start_time = time.time()
            result = subprocess.run(
                command,
                shell=use_shell,
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=timeout,
            )
            duration = time.time() - start_time

            if result.returncode == 0:
                logger.info(f"Command hook succeeded: {command}")
                return HookResult(
                    success=True,
                    output=result.stdout,
                    duration=duration,
                )
            else:
                logger.warning(f"Command hook failed: {command}")
                return HookResult(
                    success=False,
                    output=result.stdout,
                    error=result.stderr,
                    duration=duration,
                )
        except subprocess.TimeoutExpired:
            logger.error(f"Command hook timeout: {command}")
            return HookResult(success=False, error=f"Command timeout after {timeout}s")
        except Exception as e:
            logger.error(f"Command hook error: {e}")
            return HookResult(success=False, error=str(e))

    def _execute_api(self, hook: Hook, context: dict[str, Any] | None) -> HookResult:
        """执行 API 类型 hook"""
        import time

        try:
            import requests
        except ImportError:
            return HookResult(success=False, error="requests module not installed")

        method = hook.config.get("method", "GET").upper()
        url = hook.config.get("url", "")
        headers = hook.config.get("headers", {})
        body = hook.config.get("body")
        timeout = hook.config.get("timeout", 30)
        expected_status = hook.config.get("expected_status")

        if not url:
            return HookResult(success=False, error="URL not specified")

        try:
            start_time = time.time()
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=body,
                timeout=timeout,
            )
            duration = time.time() - start_time

            if expected_status and response.status_code != expected_status:
                return HookResult(
                    success=False,
                    output=response.text,
                    error=f"Expected status {expected_status}, got {response.status_code}",
                    duration=duration,
                )

            logger.info(f"API hook succeeded: {method} {url}")
            return HookResult(
                success=True,
                output=response.text,
                duration=duration,
            )
        except Exception as e:
            logger.error(f"API hook error: {e}")
            return HookResult(success=False, error=str(e))

    def _execute_sql(self, hook: Hook, context: dict[str, Any] | None) -> HookResult:
        """执行 SQL 类型 hook"""
        db_type = hook.config.get("db_type", "sqlite")
        connection_string = hook.config.get("connection_string", "")
        query = hook.config.get("query", "")

        if not query:
            return HookResult(success=False, error="SQL query not specified")

        if not hook.config.get("allow_unsafe_sql", False):
            logger.warning(
                f"Executing user-provided SQL: {query[:50]}... "
                "Set 'allow_unsafe_sql: true' in hook config to suppress this warning."
            )

        try:
            start_time = time.time()

            if db_type == "sqlite":
                conn = sqlite3.connect(connection_string or ":memory:")
                try:
                    cursor = conn.cursor()
                    cursor.execute(query)
                    conn.commit()
                    result = cursor.fetchall()
                finally:
                    conn.close()

                duration = time.time() - start_time
                logger.info(f"SQL hook succeeded: {query[:50]}...")
                return HookResult(
                    success=True,
                    output=str(result),
                    duration=duration,
                )
            elif db_type == "mysql":
                try:
                    import pymysql
                except ImportError:
                    return HookResult(success=False, error="pymysql not installed")

                conn = pymysql.connect(**connection_string)
                try:
                    cursor = conn.cursor()
                    cursor.execute(query)
                    conn.commit()
                    result = cursor.fetchall()
                finally:
                    conn.close()

                duration = time.time() - start_time
                logger.info(f"SQL hook succeeded: {query[:50]}...")
                return HookResult(
                    success=True,
                    output=str(result),
                    duration=duration,
                )
            else:
                return HookResult(
                    success=False, error=f"Unsupported database type: {db_type}"
                )
        except Exception as e:
            logger.error(f"SQL hook error: {e}")
            return HookResult(success=False, error=str(e))

    def _execute_function(
        self, hook: Hook, context: dict[str, Any] | None
    ) -> HookResult:
        """执行函数类型 hook"""
        module_name = hook.config.get("module", "")
        function_name = hook.config.get("function", "")
        args = hook.config.get("args", [])
        kwargs = hook.config.get("kwargs", {})

        if not module_name or not function_name:
            return HookResult(success=False, error="Module or function not specified")

        try:
            start_time = time.time()
            module = __import__(module_name, fromlist=[function_name])
            func = getattr(module, function_name)
            result = func(*args, **kwargs)
            duration = time.time() - start_time

            logger.info(f"Function hook succeeded: {module_name}.{function_name}")
            return HookResult(
                success=True,
                output=str(result),
                duration=duration,
            )
        except Exception as e:
            logger.error(f"Function hook error: {e}")
            return HookResult(success=False, error=str(e))

    def execute_hooks(
        self,
        hooks: list[Hook],
        when: HookWhen,
        test_passed: bool = True,
        context: dict[str, Any] | None = None,
    ) -> tuple[bool, list[HookResult]]:
        """
        批量执行 hooks

        Args:
            hooks: Hook 列表
            when: 执行时机（setup/teardown）
            test_passed: 测试是否通过（影响 only_on_success）
            context: 执行上下文

        Returns:
            (全部成功, 结果列表)
        """
        results = []
        all_success = True

        for hook in hooks:
            if hook.when != when:
                continue

            if hook.only_on_success and not test_passed:
                logger.info(
                    f"Skipping hook {hook.name}: test failed and only_on_success=True"
                )
                continue

            result = self.execute_hook(hook, context)
            results.append(result)

            if not result.success:
                all_success = False
                if when == HookWhen.SETUP:
                    logger.error(f"Setup hook failed: {hook.name}")
                    break

        return all_success, results


class HookManager:
    """Hook 管理器 - 从用例数据解析和管理 hooks"""

    @staticmethod
    def parse_hooks(case_data: dict[str, Any]) -> tuple[list[Hook], list[Hook]]:
        """
        从用例数据中解析 hooks

        Returns:
            (setup_hooks, teardown_hooks)
        """
        setup_hooks = []
        teardown_hooks = []

        hooks_data = case_data.get("hooks", [])
        for hook_data in hooks_data:
            try:
                hook = Hook.from_dict(hook_data)
                if hook.when == HookWhen.SETUP:
                    setup_hooks.append(hook)
                elif hook.when == HookWhen.TEARDOWN:
                    teardown_hooks.append(hook)
            except Exception as e:
                logger.warning(f"Failed to parse hook: {e}")

        return setup_hooks, teardown_hooks

    @staticmethod
    def parse_legacy_setup_teardown(
        case_data: dict[str, Any],
    ) -> tuple[list[Hook], list[Hook]]:
        """
        兼容旧版 setup/teardown 格式

        支持格式:
        - setup: {command: "..."}
        - teardown: {command: "..."}
        """
        setup_hooks = []
        teardown_hooks = []

        if "setup" in case_data:
            setup_data = case_data["setup"]
            if isinstance(setup_data, dict):
                hook = Hook(
                    type=HookType.COMMAND,
                    when=HookWhen.SETUP,
                    config=setup_data,
                    name="legacy_setup",
                )
                setup_hooks.append(hook)

        if "teardown" in case_data:
            teardown_data = case_data["teardown"]
            if isinstance(teardown_data, dict):
                hook = Hook(
                    type=HookType.COMMAND,
                    when=HookWhen.TEARDOWN,
                    config=teardown_data,
                    name="legacy_teardown",
                    always_run=True,
                )
                teardown_hooks.append(hook)

        return setup_hooks, teardown_hooks
