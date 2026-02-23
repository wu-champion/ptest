# -*- coding: utf-8 -*-
"""Week 5-6 功能测试 / Week 5-6 Feature Tests"""

import pytest
import time


class TestMockServer:
    """Mock服务器测试"""

    def test_mock_route_creation(self):
        """测试Mock路由创建"""
        from ptest.mock import MockRoute

        route = MockRoute(
            path="/api/test",
            method="GET",
            response={"status": 200, "body": {"message": "success"}},
        )

        assert route.path == "/api/test"
        assert route.method == "GET"
        assert route.response["status"] == 200

    def test_mock_config_serialization(self):
        """测试Mock配置序列化"""
        from ptest.mock import MockConfig, MockRoute

        config = MockConfig(
            name="test_server",
            host="127.0.0.1",
            port=8080,
            routes=[
                MockRoute(
                    path="/api/test",
                    method="GET",
                    response={"status": 200, "body": {"test": True}},
                )
            ],
        )

        data = config.to_dict()
        assert data["name"] == "test_server"
        assert data["port"] == 8080
        assert len(data["routes"]) == 1

        config2 = MockConfig.from_dict(data)
        assert config2.name == "test_server"
        assert config2.port == 8080

    def test_mock_request_record(self):
        """测试Mock请求记录"""
        from ptest.mock import MockRequest

        request = MockRequest(
            method="POST",
            path="/api/test",
            headers={"Content-Type": "application/json"},
            body={"key": "value"},
        )

        assert request.method == "POST"
        assert request.path == "/api/test"
        assert request.headers["Content-Type"] == "application/json"


class TestParallelExecution:
    """并行执行测试"""

    def test_dependency_resolver(self):
        """测试依赖解析器"""
        from ptest.execution import DependencyResolver

        dependencies = {
            "task_c": ["task_a", "task_b"],
            "task_d": ["task_c"],
        }

        resolver = DependencyResolver(dependencies)

        task_ids = ["task_a", "task_b", "task_c", "task_d"]
        ready = resolver.get_ready_tasks(task_ids)
        assert "task_a" in ready
        assert "task_b" in ready

        resolver.mark_completed("task_a")
        resolver.mark_completed("task_b")

        ready = resolver.get_ready_tasks(task_ids)
        assert "task_c" in ready

    def test_dependency_resolver_topological_sort(self):
        """测试依赖拓扑排序"""
        from ptest.execution import DependencyResolver

        dependencies = {
            "task_c": ["task_a", "task_b"],
            "task_d": ["task_c"],
        }

        resolver = DependencyResolver(dependencies)
        task_ids = ["task_a", "task_b", "task_c", "task_d"]

        layers = resolver.get_execution_order(task_ids)

        assert len(layers[0]) == 2
        assert "task_a" in layers[0]
        assert "task_b" in layers[0]
        assert len(layers[1]) == 1
        assert "task_c" in layers[1]
        assert len(layers[2]) == 1
        assert "task_d" in layers[2]

    def test_execution_task(self):
        """测试执行任务"""
        from ptest.execution import ExecutionTask, TaskStatus

        def sample_func():
            return "result"

        task = ExecutionTask(
            task_id="test_task",
            func=sample_func,
        )

        assert task.task_id == "test_task"
        assert task.status == TaskStatus.PENDING

    def test_execution_result(self):
        """测试执行结果"""
        from ptest.execution import ExecutionResult

        result = ExecutionResult(
            task_id="test_task",
            success=True,
            result="test_data",
            duration=1.5,
        )

        assert result.task_id == "test_task"
        assert result.success is True
        assert result.duration == 1.5

    def test_sequential_executor(self):
        """测试串行执行器"""
        from ptest.execution import SequentialExecutor, ExecutionTask

        executor = SequentialExecutor()

        results = []

        def task_func(x):
            results.append(x)
            return x * 2

        tasks = [
            ExecutionTask(task_id="task_1", func=lambda: task_func(1)),
            ExecutionTask(task_id="task_2", func=lambda: task_func(2)),
            ExecutionTask(task_id="task_3", func=lambda: task_func(3)),
        ]

        execution_results = executor.execute(tasks)

        assert len(execution_results) == 3
        assert all(r.success for r in execution_results)

    def test_parallel_executor(self):
        """测试并行执行器"""
        from ptest.execution import ParallelExecutor, ExecutionTask

        executor = ParallelExecutor(max_workers=2)

        def slow_task(duration):
            time.sleep(duration)
            return duration

        tasks = [
            ExecutionTask(task_id="task_1", func=lambda: slow_task(0.1)),
            ExecutionTask(task_id="task_2", func=lambda: slow_task(0.1)),
        ]

        start_time = time.time()
        results = executor.execute(tasks)
        elapsed = time.time() - start_time

        # 并行执行应该接近单个任务时间，但允许一定波动
        assert elapsed < 0.35
        assert len(results) == 2
        assert all(r.success for r in results)

        executor.shutdown()


class TestFixtures:
    """Fixtures测试"""

    def test_fixture_scope_enum(self):
        """测试Fixture作用域枚举"""
        from ptest.fixtures import FixtureScope

        assert FixtureScope.SESSION.value == "session"
        assert FixtureScope.FUNCTION.value == "function"

    def test_fixture_creation(self):
        """测试Fixture创建"""
        from ptest.fixtures import Fixture, FixtureScope

        def sample_fixture():
            return "test_value"

        fixture = Fixture(
            name="test_fixture",
            scope=FixtureScope.FUNCTION,
            func=sample_fixture,
        )

        assert fixture.name == "test_fixture"
        assert fixture.scope == FixtureScope.FUNCTION

    def test_fixture_manager_singleton(self):
        """测试Fixture管理器单例模式"""
        from ptest.fixtures import FixtureManager

        manager1 = FixtureManager()
        manager2 = FixtureManager()

        assert manager1 is manager2

    def test_fixture_decorator(self):
        """测试Fixture装饰器"""
        from ptest.fixtures import fixture, get_fixture_manager

        @fixture(scope="function")
        def test_data():
            return {"key": "value"}

        manager = get_fixture_manager()
        value = manager.get_or_create("test_data")

        assert value == {"key": "value"}


class TestReportEnhanced:
    """增强报告测试"""

    def test_test_result_dataclass(self):
        """测试TestResult数据类"""
        from ptest.reports.enhanced_generator import TestResult

        result = TestResult(
            case_id="test_001",
            status="passed",
            duration=0.5,
            error_message="",
        )

        assert result.case_id == "test_001"
        assert result.status == "passed"
        assert result.duration == 0.5

    def test_report_data_dataclass(self):
        """测试ReportData数据类"""
        from ptest.reports.enhanced_generator import ReportData, TestResult

        results = [
            TestResult("test_1", "passed", 0.5),
            TestResult("test_2", "failed", 1.0),
        ]

        data = ReportData(
            title="Test Report",
            total=2,
            passed=1,
            failed=1,
            duration=1.5,
            results=results,
        )

        assert data.title == "Test Report"
        assert data.total == 2
        assert data.passed == 1
        assert data.failed == 1

    def test_enhanced_report_generator_init(self):
        """测试增强报告生成器初始化"""
        from ptest.reports.enhanced_generator import EnhancedReportGenerator

        generator = EnhancedReportGenerator(output_dir="test_reports")

        assert generator.output_dir.name == "test_reports"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
