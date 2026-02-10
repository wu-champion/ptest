# -*- coding: utf-8 -*-
"""集成测试 - 完整工作流 / Integration Tests - Complete Workflow"""

import json
import tempfile
from pathlib import Path

import pytest


class TestCompleteWorkflow:
    """完整工作流集成测试"""

    def test_data_to_contract_workflow(self):
        """测试数据生成到契约验证工作流"""
        from ptest.data import DataGenerator
        from ptest.contract import ContractManager

        # 1. 生成测试数据
        generator = DataGenerator()
        test_data = generator.generate("name", count=5, format="raw")
        assert len(test_data) == 5

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
            assert "test_api" in contracts

    def test_suite_execution_workflow(self):
        """测试套件执行工作流"""
        from ptest.suites import SuiteManager, TestSuite, CaseRef, ExecutionMode

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
            assert suite.name == "integration_suite"

            # 3. 加载并验证
            loaded = manager.load_suite("integration_suite")
            assert loaded is not None
            assert len(loaded.cases) == 2

            # 4. 验证依赖关系
            sorted_cases = loaded.get_sorted_cases()
            assert sorted_cases[0].case_id == "test_login"
            assert sorted_cases[1].case_id == "test_api"

    def test_config_to_execution_workflow(self):
        """测试配置到执行工作流"""
        from ptest.config import Config

        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. 创建配置
            config = Config(name="test_project")
            config.set("log_level", "INFO")
            config.set("timeout", 300)
            config.set("parallel", True)

            # 2. 保存配置
            config_file = Path(tmpdir) / "config.yaml"
            config.save(config_file)

            # 3. 加载配置
            loaded = Config.load(config_file)
            assert loaded.get("log_level") == "INFO"
            assert loaded.get("timeout") == 300
            assert loaded.get("parallel") is True


class TestModuleIntegration:
    """模块间集成测试"""

    def test_data_generator_with_templates(self):
        """测试数据生成器与模板集成"""
        from ptest.data import DataGenerator, DataTemplate

        # 1. 创建模板
        template = DataTemplate(name="user_template")
        template.fields = {
            "name": "{{name}}",
            "email": "{{email}}",
            "age": "{{integer:18,65}}",
        }

        # 2. 使用模板生成数据
        generator = DataGenerator()
        # 模板系统应该支持变量替换

    def test_execution_with_hooks(self):
        """测试执行器与Hooks集成"""
        from ptest.cases.hooks import (
            Hook,
            HookActionType,
            HookExecutor,
            HookManager,
            HookType,
        )
        from ptest.execution import ExecutionTask, SequentialExecutor

        # 1. 创建Hook
        setup_hook = Hook(
            name="setup",
            hook_type=HookType.SETUP,
            action_type=HookActionType.COMMAND,
            action_params={"command": "echo setup"},
        )

        # 2. 创建Hook管理器
        hook_manager = HookManager()
        hook_manager.register(setup_hook)

        # 3. 执行Hook
        executor = HookExecutor()
        results = hook_manager.execute_hooks(HookType.SETUP, executor)

        assert len(results) == 1
        assert results[0].success is True

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
        assert server.config.name == "test_mock"
        assert len(server.config.routes) == 1


class TestEndToEndScenarios:
    """端到端场景测试"""

    def test_api_testing_scenario(self):
        """API测试场景"""
        # 场景: 契约导入 -> 数据生成 -> Mock服务 -> 执行测试
        from ptest.data import DataGenerator
        from ptest.mock import MockConfig, MockServer

        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. 生成测试数据
            generator = DataGenerator()
            user_data = generator.generate("email", count=3, format="raw")
            assert len(user_data) == 3

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
            assert len(server.config.routes) == 1

    def test_database_testing_scenario(self):
        """数据库测试场景"""
        from ptest.data import DataGenerator

        # 1. 生成数据库测试数据
        generator = DataGenerator()

        # 生成用户数据
        names = generator.generate("name", count=10, format="raw")
        emails = generator.generate("email", count=10, format="raw")

        assert len(names) == 10
        assert len(emails) == 10

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

        assert len(execution_results) == 5
        assert all(r.success for r in execution_results)

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
            with pytest.raises(Exception):
                manager.import_contract(str(contract_file), "invalid")

    def test_suite_validation_error(self):
        """测试套件验证错误"""
        from ptest.suites import TestSuite, CaseRef

        # 创建无效套件（循环依赖）
        suite = TestSuite(
            name="invalid_suite",
            cases=[
                CaseRef(case_id="case_a", order=1, depends_on=["case_b"]),
                CaseRef(case_id="case_b", order=2, depends_on=["case_a"]),
            ],
        )

        # 验证应该失败
        is_valid, errors = suite.validate()
        assert is_valid is False

    def test_hook_execution_failure(self):
        """测试Hook执行失败"""
        from ptest.cases.hooks import Hook, HookActionType, HookExecutor, HookType

        # 创建会失败的Hook
        hook = Hook(
            name="failing_hook",
            hook_type=HookType.SETUP,
            action_type=HookActionType.COMMAND,
            action_params={"command": "exit 1"},
            ignore_failure=False,
        )

        executor = HookExecutor()
        result = executor.execute(hook)

        assert result.success is False
        assert result.error is not None
