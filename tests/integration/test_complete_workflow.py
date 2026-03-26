# -*- coding: utf-8 -*-
"""集成测试 - 完整工作流 - ptest 断言版本

迁移说明:
- 原文件使用 pytest/unittest 断言，现已迁移到 ptest 断言
- 迁移对照表:
  - assert x == y → assert_that(x).equals(y)
  - assert x in y → assert_that(y).contains(x)
  - assert len(x) == n → assert_that(len(x)).equals(n)
  - assert x is not None → assert_that(x).not_none()
  - assert x is True → assert_that(x).is_true()
  - pytest.raises(E) → assert_raises(E)
"""

import json
import tempfile
from pathlib import Path


from ptest.assertions import assert_that, assert_raises


class TestCompleteWorkflow:
    """完整工作流集成测试"""

    def test_data_to_contract_workflow(self):
        """测试数据生成到契约验证工作流"""
        from ptest.data import DataGenerator
        from ptest.contract import ContractManager

        # 1. 生成测试数据
        generator = DataGenerator()
        test_data = generator.generate("name", count=5, format="raw")
        assert_that(len(test_data)).equals(5)

        # 2. 创建契约
        contract_data = {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {
                "/users": {
                    "get": {
                        "responses": {
                            "200": {
                                "description": "Success",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {"name": {"type": "string"}},
                                        }
                                    }
                                },
                            }
                        }
                    }
                }
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            # 3. 保存契约
            contract_file = Path(tmpdir) / "contract.json"
            contract_file.write_text(json.dumps(contract_data))

            # 4. 导入契约
            manager = ContractManager(storage_dir=tmpdir)
            manager.import_contract(str(contract_file), "test_api")

            # 5. 验证契约存在
            contracts = manager.list_contracts()
            assert_that("test_api" in contracts).is_true()

    def test_suite_execution_workflow(self):
        """测试套件执行工作流"""
        from ptest.suites import SuiteManager

        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. 创建套件管理器
            manager = SuiteManager(storage_dir=tmpdir)

            # 2. 创建测试套件
            suite_data = {
                "name": "integration_suite",
                "description": "Integration test suite",
                "cases": [
                    {"case_id": "test_login", "order": 1},
                    {"case_id": "test_api", "order": 2, "depends_on": ["test_login"]},
                ],
                "execution_mode": "sequential",
            }

            suite = manager.create_suite(suite_data)
            assert_that(suite.name).equals("integration_suite")

            # 3. 加载并验证
            loaded = manager.load_suite("integration_suite")
            assert_that(loaded).not_none()
            assert_that(len(loaded.cases)).equals(2)

            # 4. 验证依赖关系
            sorted_cases = loaded.get_sorted_cases()
            assert_that(sorted_cases[0].case_id).equals("test_login")
            assert_that(sorted_cases[1].case_id).equals("test_api")

    def test_config_workflow(self):
        """测试配置工作流 - 使用实际config模块"""
        from ptest import config

        # 验证默认配置存在
        assert_that("log_level" in config.DEFAULT_CONFIG).is_true()
        assert_that(config.DEFAULT_CONFIG["log_level"]).equals("INFO")
        assert_that("report_format" in config.DEFAULT_CONFIG).is_true()


class TestModuleIntegration:
    """模块间集成测试"""

    def test_data_generator_with_templates(self):
        """测试数据生成器与模板集成 - 使用正确的API"""
        from ptest.data import DataTemplate

        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. 创建模板管理器
            template_manager = DataTemplate(templates_dir=tmpdir)

            # 2. 保存模板
            template_data = {
                "name": "{{name}}",
                "email": "{{email}}",
                "age": "{{integer:18,65}}",
            }
            template_manager.save_template("user_template", template_data)

            # 3. 加载模板
            loaded = template_manager.load_template("user_template")
            assert_that(loaded).not_none()
            assert_that("name" in loaded).is_true()

            # 4. 列出模板
            templates = template_manager.list_templates()
            assert_that("user_template" in templates).is_true()

    def test_execution_with_hooks(self):
        """测试执行器与Hooks集成 - 使用正确的API"""
        from ptest.cases.hooks import (
            Hook,
            HookType,
            HookWhen,
            HookExecutor,
        )
        from ptest.environment import EnvironmentManager

        # 创建环境管理器
        env_manager = EnvironmentManager()

        # 1. 创建Hook (使用正确的API) - 使用列表格式命令
        setup_hook = Hook(
            name="setup",
            type=HookType.COMMAND,
            when=HookWhen.SETUP,
            config={"command": ["echo", "setup"]},
        )

        # 2. 创建Hook执行器
        executor = HookExecutor(env_manager)

        # 3. 执行单个Hook
        result = executor.execute_hook(setup_hook)

        assert_that(result.success).is_true()
        assert_that("setup" in result.output.lower()).is_true()

        # 4. 批量执行Hooks
        hooks = [
            Hook(
                type=HookType.COMMAND,
                when=HookWhen.SETUP,
                config={"command": ["echo", "1"]},
            ),
            Hook(
                type=HookType.COMMAND,
                when=HookWhen.SETUP,
                config={"command": ["echo", "2"]},
            ),
        ]
        all_success, results = executor.execute_hooks(hooks, HookWhen.SETUP)

        assert_that(all_success).is_true()
        assert_that(len(results)).equals(2)

    def test_mock_with_data_flow(self):
        """测试Mock服务与数据流集成"""
        from ptest.mock import MockConfig, MockRoute, MockServer

        # 1. 创建Mock配置
        config = MockConfig(
            name="test_mock",
            port=18080,
            routes=[
                MockRoute(
                    path="/api/data",
                    method="GET",
                    response={"status": 200, "body": {"data": [1, 2, 3]}},
                )
            ],
        )

        # 2. 创建Mock服务器
        server = MockServer(config)
        assert_that(server.config.name).equals("test_mock")
        assert_that(len(server.config.routes)).equals(1)


class TestEndToEndScenarios:
    """端到端场景测试"""

    def test_api_testing_scenario(self):
        """API测试场景"""
        # 场景: 契约导入 -> 数据生成 -> Mock服务 -> 执行测试
        from ptest.data import DataGenerator
        from ptest.mock import MockConfig, MockServer

        # 1. 生成测试数据
        generator = DataGenerator()
        user_data = generator.generate("email", count=3, format="raw")
        assert_that(len(user_data)).equals(3)

        # 2. 设置Mock服务
        config = MockConfig(name="api_mock", port=18081)
        server = MockServer(config)

        # 3. 添加Mock路由
        server.add_route(
            path="/api/users",
            method="POST",
            response={"status": 201, "body": {"id": "123", "created": True}},
        )

        # 验证配置
        assert_that(len(server.config.routes)).equals(1)

    def test_database_testing_scenario(self):
        """数据库测试场景"""
        from ptest.data import DataGenerator

        # 1. 生成数据库测试数据
        generator = DataGenerator()

        # 生成用户数据
        names = generator.generate("name", count=10, format="raw")
        emails = generator.generate("email", count=10, format="raw")

        assert_that(len(names)).equals(10)
        assert_that(len(emails)).equals(10)

    def test_parallel_execution_scenario(self):
        """并行执行场景"""
        from ptest.execution import ExecutionTask, ParallelExecutor

        results = []

        def task_func(x):
            results.append(x)
            return x * 2

        # 创建任务
        tasks = [
            ExecutionTask(task_id=f"task_{i}", func=lambda i=i: task_func(i))
            for i in range(5)
        ]

        # 并行执行
        executor = ParallelExecutor(max_workers=3)
        execution_results = executor.execute(tasks)

        assert_that(len(execution_results)).equals(5)
        assert_that(all(r.success for r in execution_results)).is_true()

        executor.shutdown()


class TestErrorHandling:
    """错误处理集成测试"""

    def test_invalid_contract_handling(self):
        """测试无效契约处理"""
        from ptest.contract import ContractManager

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ContractManager(storage_dir=tmpdir)

            # 尝试导入无效契约
            invalid_contract = {"invalid": "data"}
            contract_file = Path(tmpdir) / "invalid.json"
            contract_file.write_text(json.dumps(invalid_contract))

            # 应该抛出异常或返回错误
            with assert_raises(Exception):
                manager.import_contract(str(contract_file), "invalid")

    def test_suite_validation_error(self):
        """测试套件验证错误 - 使用实际验证逻辑"""
        from ptest.suites import TestSuite

        # 创建无效套件（缺少用例）
        suite = TestSuite(
            name="invalid_suite",
            cases=[],  # 空用例列表
        )

        # 验证应该失败
        is_valid, errors = suite.validate()
        assert_that(is_valid).is_false()
        # 检查是否有包含"至少需要一个用例"的错误
        has_error = any("至少需要一个用例" in error for error in errors)
        assert_that(has_error).is_true()

    def test_hook_execution_failure(self):
        """测试Hook执行失败 - 使用正确的API"""
        from ptest.cases.hooks import Hook, HookType, HookWhen, HookExecutor
        from ptest.environment import EnvironmentManager

        # 创建环境管理器
        env_manager = EnvironmentManager()

        # 创建会失败的Hook (使用正确的API)
        hook = Hook(
            name="failing_hook",
            type=HookType.COMMAND,
            when=HookWhen.SETUP,
            config={"command": ["exit", "1"]},
            only_on_success=False,
        )

        # 创建执行器并执行
        executor = HookExecutor(env_manager)
        result = executor.execute_hook(hook)

        assert_that(result.success).is_false()
        # result.error 可以是 None 或空字符串
        assert_that(result.error is not None or result.error == "").is_true()
