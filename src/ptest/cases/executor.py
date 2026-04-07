# ptest/cases/executor.py
"""
测试用例执行器
实现真实的测试执行逻辑，支持多种测试类型
"""

import json
import sqlite3
from typing import Dict, Any, Tuple, Union
from datetime import datetime
from .result import TestCaseResult
from .hooks import HookExecutor, HookManager, HookWhen

# 导入断言工厂
from ptest.assertions.factory import AssertionFactory


# 尝试导入可选依赖
try:
    import requests

    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    import pymysql  # type: ignore[import-untyped]

    PYMYSQL_AVAILABLE = True
except ImportError:
    PYMYSQL_AVAILABLE = False


class TestExecutor:
    """测试用例执行器"""

    def __init__(self, env_manager):
        self.env_manager = env_manager
        self.hook_executor = HookExecutor(env_manager)

    def execute_case(self, case_id: str, case_data: Dict[str, Any]) -> TestCaseResult:
        """
        执行测试用例（包含 setup/teardown hooks）
        根据用例类型分发到具体的执行方法
        """
        result = TestCaseResult(case_id)
        result.start_time = datetime.now()

        # 解析 hooks
        setup_hooks, teardown_hooks = HookManager.parse_hooks(case_data)
        legacy_setup, legacy_teardown = HookManager.parse_legacy_setup_teardown(
            case_data
        )
        setup_hooks.extend(legacy_setup)
        teardown_hooks.extend(legacy_teardown)

        setup_success = True
        test_success = True
        setup_results = []
        test_output = ""

        try:
            # 1. 执行 setup hooks
            if setup_hooks:
                self.env_manager.logger.info(
                    f"Executing {len(setup_hooks)} setup hooks for {case_id}"
                )
                setup_success, setup_results = self.hook_executor.execute_hooks(
                    setup_hooks, HookWhen.SETUP, context=case_data
                )

            if not setup_success:
                # Setup 失败，跳过测试
                result.status = "failed"
                result.error_message = f"Setup hooks failed: {[r.error for r in setup_results if not r.success]}"
                test_success = False
            else:
                # 2. 执行测试
                test_type = case_data.get("type", "").lower()

                if test_type == "api":
                    test_success, test_output = self._execute_api_test(case_data)
                elif test_type == "database":
                    test_success, test_output = self._execute_database_test(case_data)
                elif test_type == "web":
                    test_success, test_output = self._execute_web_test(case_data)
                elif test_type == "service":
                    test_success, test_output = self._execute_service_test(case_data)
                else:
                    test_success, test_output = (
                        False,
                        f"Unsupported test type: {test_type}",
                    )

                if test_success:
                    result.status = "passed"
                else:
                    result.status = "failed"
                    result.error_message = str(test_output)

        except Exception as e:
            test_success = False
            result.status = "error"
            result.error_message = f"Test execution error: {str(e)}"
            self.env_manager.logger.error(f"Case '{case_id}' execution error: {str(e)}")

        finally:
            # 3. 始终执行 teardown hooks
            if teardown_hooks:
                self.env_manager.logger.info(
                    f"Executing {len(teardown_hooks)} teardown hooks for {case_id}"
                )
                _, teardown_results = self.hook_executor.execute_hooks(
                    teardown_hooks,
                    HookWhen.TEARDOWN,
                    test_passed=test_success,
                    context=case_data,
                )

            result.end_time = datetime.now()
            result.duration = (result.end_time - result.start_time).total_seconds()
            if not result.error_message:
                result.output = (
                    test_output if not isinstance(test_output, str) else test_output
                )

        return result

    def _execute_api_test(self, case_data: Dict[str, Any]) -> Tuple[bool, Any]:
        """执行API测试

        支持两种格式:
        1. 新 DSL 格式: request/assertions 结构
        2. 旧扁平格式: method/url/expected_status 等字段
        """
        if not REQUESTS_AVAILABLE:
            return False, "requests module not installed. Run: pip install requests"

        try:
            # 优先使用新 DSL 格式 (request/assertions)
            request_config = case_data.get("request", {})
            assertions_config = case_data.get("assertions", [])

            # 解析请求参数 (新格式优先，否则使用旧格式)
            method = request_config.get("method", "") or case_data.get("method", "GET")
            url = request_config.get("url", "") or case_data.get("url", "")
            headers = request_config.get("headers", {}) or case_data.get("headers", {})
            params = request_config.get("params", {}) or case_data.get("params", {})
            body = request_config.get("body", {}) or case_data.get("body", {})
            timeout = request_config.get("timeout", 30) or case_data.get("timeout", 30)

            # 确保 method 是大写
            if method:
                method = method.upper()

            # 如果没有请求配置且没有 url，报错
            if not url:
                return False, "Missing URL: please provide 'request.url' or 'url'"

            self.env_manager.logger.info(f"Executing API test: {method} {url}")

            # 发送HTTP请求
            response = requests.request(  # type: ignore
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=body if body else None,
                timeout=timeout,
            )

            # 如果有 assertions 配置，使用断言系统
            if assertions_config:
                return self._execute_assertions(response, assertions_config)

            # 没有 assertions 配置，回退到旧逻辑 (保持向后兼容)
            expected_status = case_data.get("expected_status", 200)
            expected_response = case_data.get("expected_response", {})

            # 检查状态码
            if response.status_code != expected_status:
                return (
                    False,
                    f"Expected status {expected_status}, got {response.status_code}",
                )

            # 检查响应内容
            if expected_response:
                try:
                    actual_response = response.json()
                    if not self._compare_response(expected_response, actual_response):
                        return (
                            False,
                            f"Response mismatch. Expected: {expected_response}, Actual: {actual_response}",
                        )
                except json.JSONDecodeError:
                    return False, f"Expected JSON response, got: {response.text}"

            return True, response.json() if response.headers.get(
                "content-type", ""
            ).startswith("application/json") else response.text

        except requests.exceptions.Timeout:  # type: ignore
            return False, f"Request timeout after {case_data.get('timeout', 30)}s"
        except requests.exceptions.ConnectionError:  # type: ignore
            return (
                False,
                f"Connection error: Unable to connect to {case_data.get('url', 'unknown')}",
            )
        except Exception as e:
            return False, f"API test error: {str(e)}"

    def _execute_assertions(
        self, response, assertions_config: list
    ) -> Tuple[bool, Any]:
        """执行断言列表

        Args:
            response: HTTP 响应对象
            assertions_config: 断言配置列表

        Returns:
            (success, message) 元组
        """

        failed_assertions = []
        passed_count = 0

        # 准备实际值
        actual_value = response
        actual_json = None

        # 尝试解析 JSON 响应
        content_type = response.headers.get("content-type", "")
        if content_type.startswith("application/json"):
            try:
                actual_json = response.json()
            except Exception:
                pass

        for idx, assertion_item in enumerate(assertions_config):
            if not isinstance(assertion_item, dict):
                failed_assertions.append(f"Assertion {idx}: invalid format")
                continue

            assertion_type = assertion_item.get("type", "")
            if not assertion_type:
                failed_assertions.append(f"Assertion {idx}: missing 'type'")
                continue

            try:
                # 根据断言类型准备 actual 值
                if assertion_type in ("status_code", "statuscode"):
                    actual = response.status_code
                    expected = assertion_item.get("expected")
                    kwargs = {}
                elif assertion_type in ("json_path", "jsonpath"):
                    actual = actual_json if actual_json is not None else {}
                    expected = assertion_item.get("expected")
                    kwargs = {"path": assertion_item.get("path", "")}
                elif assertion_type in ("body", "bodyassertion"):
                    actual = response.text
                    expected = assertion_item.get("expected")
                    kwargs = {}
                elif assertion_type in ("header", "headerassertion"):
                    actual = dict(response.headers)
                    expected = assertion_item.get("expected")
                    kwargs = {"header_name": assertion_item.get("header", "")}
                elif assertion_type in ("regex", "regexassertion"):
                    actual = response.text
                    expected = assertion_item.get("expected")
                    kwargs = {}
                elif assertion_type in ("schema", "schemaassertion"):
                    actual = actual_json if actual_json is not None else {}
                    expected = assertion_item.get("expected")
                    kwargs = {"schema": assertion_item.get("schema", {})}
                else:
                    # 通用处理
                    actual = actual_value
                    expected = assertion_item.get("expected")
                    kwargs = {
                        k: v
                        for k, v in assertion_item.items()
                        if k not in ("type", "expected", "description")
                    }

                # 创建并执行断言
                assertion = AssertionFactory.create(assertion_type)
                result = assertion.assert_value(actual, expected=expected, **kwargs)

                if result.passed:
                    passed_count += 1
                else:
                    error_msg = (
                        f"Assertion {idx} ({assertion_type}) failed: {result.message}"
                    )
                    if result.extra:
                        error_msg += f" - {result.extra}"
                    failed_assertions.append(error_msg)

            except ValueError as e:
                failed_assertions.append(
                    f"Assertion {idx} ({assertion_type}): {str(e)}"
                )
            except Exception as e:
                failed_assertions.append(
                    f"Assertion {idx} ({assertion_type}): unexpected error: {str(e)}"
                )

        # 返回结果
        if failed_assertions:
            return (
                False,
                f"{len(failed_assertions)} assertion(s) failed: {'; '.join(failed_assertions[:3])}",
            )
        else:
            return True, f"{passed_count} assertion(s) passed"

    def _execute_database_test(self, case_data: Dict[str, Any]) -> Tuple[bool, Any]:
        """执行数据库测试"""
        try:
            db_type = case_data.get("db_type", "mysql").lower()
            host = case_data.get("host", "localhost")
            port = case_data.get("port", 3306)
            database = case_data.get("database", "")
            username = case_data.get("username", "root")
            password = case_data.get("password", "")
            query = case_data.get("query", "")
            expected_result = case_data.get("expected_result", None)
            operations = case_data.get("operations", [])

            self.env_manager.logger.info(f"Executing database test: {db_type} {query}")

            if db_type == "mysql":
                if isinstance(operations, list) and operations:
                    return self._execute_mysql_operations(
                        host, port, database, username, password, operations
                    )
                return self._execute_mysql_query(
                    host, port, database, username, password, query, expected_result
                )
            elif db_type == "sqlite":
                if isinstance(operations, list) and operations:
                    return self._execute_sqlite_operations(database, operations)
                return self._execute_sqlite_query(database, query, expected_result)
            else:
                return False, f"Unsupported database type: {db_type}"

        except Exception as e:
            return False, f"Database test error: {str(e)}"

    def _execute_mysql_query(
        self,
        host: str,
        port: int,
        database: str,
        username: str,
        password: str,
        query: str,
        expected_result: Any,
    ) -> Tuple[bool, Any]:
        """执行MySQL查询"""
        if not PYMYSQL_AVAILABLE:
            return False, "pymysql module not installed. Run: pip install pymysql"

        try:
            connection = pymysql.connect(  # type: ignore
                host=host,
                port=port,
                user=username,
                password=password,
                database=database or None,
                charset="utf8mb4",
            )

            with connection.cursor() as cursor:
                cursor.execute(query)

                if query.strip().upper().startswith("SELECT"):
                    result = cursor.fetchall()
                    # 转换为字典列表格式
                    columns = [desc[0] for desc in cursor.description]
                    result = [dict(zip(columns, row)) for row in result]
                else:
                    connection.commit()
                    result = (
                        f"Query executed successfully. Rows affected: {cursor.rowcount}"
                    )

                connection.close()

                # 检查预期结果
                if expected_result is not None:
                    if isinstance(expected_result, dict) and "count" in expected_result:
                        expected_count = expected_result["count"]
                        actual_count = len(result) if isinstance(result, list) else 0
                        if actual_count != expected_count:
                            return (
                                False,
                                f"Expected {expected_count} rows, got {actual_count}",
                            )
                    elif not self._compare_response(expected_result, result):
                        return (
                            False,
                            f"Result mismatch. Expected: {expected_result}, Actual: {result}",
                        )

                return True, result

        except Exception as e:
            return False, f"MySQL error: {str(e)}"

    def _execute_mysql_operations(
        self,
        host: str,
        port: int,
        database: str,
        username: str,
        password: str,
        operations: list[dict[str, Any]],
    ) -> Tuple[bool, Any]:
        """执行 MySQL 多步操作测试"""
        if not PYMYSQL_AVAILABLE:
            return False, "pymysql module not installed. Run: pip install pymysql"

        try:
            connection = pymysql.connect(  # type: ignore
                host=host,
                port=port,
                user=username,
                password=password,
                database=database or None,
                charset="utf8mb4",
            )
            success, result = self._execute_database_operations(connection, operations)
            connection.close()
            if success:
                return True, result
            return False, f"MySQL operation error: {result}"
        except Exception as e:
            return False, f"MySQL error: {str(e)}"

    def _execute_sqlite_query(
        self, database: str, query: str, expected_result: Any
    ) -> Tuple[bool, Any]:
        """执行SQLite查询"""
        try:
            connection = sqlite3.connect(database)
            connection.row_factory = sqlite3.Row

            cursor = connection.cursor()
            cursor.execute(query)

            result: Union[list[dict[str, Any]], str]
            if query.strip().upper().startswith("SELECT"):
                result = [dict(row) for row in cursor.fetchall()]
            else:
                connection.commit()
                result = (
                    f"Query executed successfully. Rows affected: {cursor.rowcount}"
                )

            connection.close()

            # 检查预期结果
            if expected_result is not None:
                if isinstance(expected_result, dict) and "count" in expected_result:
                    expected_count = expected_result["count"]

                    # 处理COUNT查询的特殊情况
                    if (
                        isinstance(result, list)
                        and len(result) == 1
                        and "count" in result[0]
                    ):
                        actual_count = result[0]["count"]
                    else:
                        actual_count = len(result) if isinstance(result, list) else 0

                    if actual_count != expected_count:
                        return (
                            False,
                            f"Expected {expected_count} rows, got {actual_count}",
                        )
                elif not self._compare_response(expected_result, result):
                    return (
                        False,
                        f"Result mismatch. Expected: {expected_result}, Actual: {result}",
                    )

            return True, result

        except Exception as e:
            return False, f"SQLite error: {str(e)}"

    def _execute_sqlite_operations(
        self,
        database: str,
        operations: list[dict[str, Any]],
    ) -> Tuple[bool, Any]:
        """执行 SQLite 多步操作测试"""
        try:
            connection = sqlite3.connect(database)
            connection.row_factory = sqlite3.Row
            success, result = self._execute_database_operations(connection, operations)
            connection.close()
            if success:
                return True, result
            return False, f"SQLite operation error: {result}"
        except Exception as e:
            return False, f"SQLite error: {str(e)}"

    def _execute_database_operations(
        self,
        connection: Any,
        operations: list[dict[str, Any]],
    ) -> Tuple[bool, Any]:
        """按顺序执行多步数据库操作并进行断言。"""
        step_results: list[dict[str, Any]] = []

        for index, operation in enumerate(operations, start=1):
            if not isinstance(operation, dict):
                return False, f"Operation {index} is not a valid mapping"

            query = str(operation.get("query", "")).strip()
            if not query:
                return False, f"Operation {index} is missing query"

            expected_result = operation.get("expected_result")
            step_name = str(operation.get("name", f"step_{index}"))

            with connection.cursor() as cursor:
                cursor.execute(query)
                result: Any
                if query.upper().startswith("SELECT"):
                    result = self._normalize_database_rows(
                        cursor.fetchall(),
                        getattr(cursor, "description", None),
                    )
                else:
                    connection.commit()
                    result = {
                        "rowcount": getattr(cursor, "rowcount", 0),
                    }

            valid, validation_message = self._validate_database_result(
                expected_result,
                result,
            )
            if not valid:
                return (
                    False,
                    f"Operation {index} ({step_name}) failed validation: {validation_message}",
                )

            step_results.append(
                {
                    "index": index,
                    "name": step_name,
                    "query": query,
                    "result": result,
                }
            )

        return True, step_results

    def _normalize_database_rows(
        self,
        rows: Any,
        description: Any,
    ) -> list[dict[str, Any]]:
        """将数据库查询结果统一转换为 dict 列表。"""
        normalized: list[dict[str, Any]] = []
        if not isinstance(rows, list):
            rows = list(rows)
        columns = [desc[0] for desc in description] if description else []
        for row in rows:
            if isinstance(row, dict):
                normalized.append(row)
            elif isinstance(row, sqlite3.Row):
                normalized.append(dict(row))
            elif columns:
                normalized.append(dict(zip(columns, row)))
            else:
                normalized.append({"value": row})
        return normalized

    def _validate_database_result(
        self,
        expected_result: Any,
        result: Any,
    ) -> Tuple[bool, str]:
        """校验数据库操作结果。"""
        if expected_result is None:
            return True, ""
        if isinstance(expected_result, dict) and "count" in expected_result:
            expected_count = expected_result["count"]
            if isinstance(result, list):
                if len(result) == 1 and "count" in result[0]:
                    actual_count = result[0]["count"]
                else:
                    actual_count = len(result)
            elif isinstance(result, dict) and "rowcount" in result:
                actual_count = result["rowcount"]
            else:
                actual_count = 0
            if actual_count != expected_count:
                return False, f"Expected {expected_count} rows, got {actual_count}"
            return True, ""
        if not self._compare_response(expected_result, result):
            return False, f"Expected {expected_result}, got {result}"
        return True, ""

    def _execute_web_test(self, case_data: Dict[str, Any]) -> Tuple[bool, Any]:
        """执行Web测试"""
        if not REQUESTS_AVAILABLE:
            return False, "requests module not installed. Run: pip install requests"

        try:
            url = case_data.get("url", "")
            expected_title = case_data.get("expected_title", "")
            expected_content = case_data.get("expected_content", "")
            timeout = case_data.get("timeout", 30)

            self.env_manager.logger.info(f"Executing web test: {url}")

            # 使用requests获取页面内容
            response = requests.get(url, timeout=timeout)  # type: ignore

            if response.status_code != 200:
                return False, f"Expected status 200, got {response.status_code}"

            content = response.text

            # 检查页面标题
            if expected_title and expected_title not in content:
                return False, f"Expected title '{expected_title}' not found"

            # 检查页面内容
            if expected_content and expected_content not in content:
                return False, f"Expected content '{expected_content}' not found"

            return True, f"Web test passed for {url}"

        except Exception as e:
            return False, f"Web test error: {str(e)}"

    def _execute_service_test(self, case_data: Dict[str, Any]) -> Tuple[bool, Any]:
        """执行服务测试"""
        try:
            service_name = case_data.get("service_name", "")
            check_type = case_data.get("check_type", "port")
            host = case_data.get("host", "localhost")
            port = case_data.get("port", 8080)
            timeout = case_data.get("timeout", 10)

            self.env_manager.logger.info(f"Executing service test: {service_name}")

            if check_type == "port":
                import socket

                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(timeout)

                result = sock.connect_ex((host, port))
                sock.close()

                if result == 0:
                    return True, f"Service {service_name} is reachable at {host}:{port}"
                else:
                    return (
                        False,
                        f"Service {service_name} is not reachable at {host}:{port}",
                    )
            else:
                return False, f"Unsupported check type: {check_type}"

        except Exception as e:
            return False, f"Service test error: {str(e)}"

    def _compare_response(self, expected: Any, actual: Any) -> bool:
        """比较预期结果和实际结果"""
        if isinstance(expected, dict) and isinstance(actual, dict):
            for key, expected_value in expected.items():
                if key not in actual:
                    return False
                if not self._compare_response(expected_value, actual[key]):
                    return False
            return True
        elif isinstance(expected, list) and isinstance(actual, list):
            if len(expected) != len(actual):
                return False
            for exp_item, act_item in zip(expected, actual):
                if not self._compare_response(exp_item, act_item):
                    return False
            return True
        else:
            return expected == actual
