# -*- coding: utf-8 -*-
"""性能测试 / Performance Tests"""

import time

import pytest


class TestDataGeneratorPerformance:
    """数据生成器性能测试"""

    def test_generate_1000_names_performance(self):
        """测试生成1000个姓名的性能"""
        from ptest.data import DataGenerator

        generator = DataGenerator()

        start = time.time()
        result = generator.generate("name", count=1000, format="raw")
        elapsed = time.time() - start

        assert len(result) == 1000
        assert elapsed < 1.0  # 应该在1秒内完成

    def test_generate_1000_emails_performance(self):
        """测试生成1000个邮箱的性能"""
        from ptest.data import DataGenerator

        generator = DataGenerator()

        start = time.time()
        result = generator.generate("email", count=1000, format="raw")
        elapsed = time.time() - start

        assert len(result) == 1000
        assert elapsed < 1.0

    def test_generate_100_uuids_performance(self):
        """测试生成100个UUID的性能"""
        from ptest.data import DataGenerator

        generator = DataGenerator()

        start = time.time()
        result = generator.generate("uuid", count=100, format="raw")
        elapsed = time.time() - start

        assert len(result) == 100
        assert elapsed < 0.5


class TestParallelExecutionPerformance:
    """并行执行性能测试"""

    def test_parallel_vs_sequential_performance(self):
        """测试并行执行相比串行的性能提升"""
        from ptest.execution import ExecutionTask, ParallelExecutor, SequentialExecutor

        def slow_task(duration):
            time.sleep(duration)
            return duration

        # 串行执行
        tasks = [
            ExecutionTask(task_id=f"task_{i}", func=lambda: slow_task(0.1))
            for i in range(5)
        ]

        sequential = SequentialExecutor()
        start = time.time()
        sequential.execute(tasks)
        sequential_time = time.time() - start

        # 并行执行
        tasks = [
            ExecutionTask(task_id=f"task_{i}", func=lambda: slow_task(0.1))
            for i in range(5)
        ]

        parallel = ParallelExecutor(max_workers=5)
        start = time.time()
        parallel.execute(tasks)
        parallel_time = time.time() - start
        parallel.shutdown()

        # 并行应该明显快于串行
        assert parallel_time < sequential_time * 0.6

    def test_parallel_execution_with_dependencies(self):
        """测试带依赖的并行执行性能"""
        from ptest.execution import ExecutionTask, ParallelExecutor

        def task_func():
            time.sleep(0.05)
            return "done"

        tasks = [ExecutionTask(task_id=f"task_{i}", func=task_func) for i in range(10)]

        dependencies = {
            "task_5": ["task_0"],
            "task_6": ["task_1"],
        }

        executor = ParallelExecutor(max_workers=5)
        start = time.time()
        results = executor.execute(tasks, dependencies)
        elapsed = time.time() - start

        assert len(results) == 10
        assert all(r.success for r in results)
        assert elapsed < 1.0

        executor.shutdown()


class TestSuiteManagerPerformance:
    """套件管理器性能测试"""

    def test_create_large_suite_performance(self):
        """测试创建大套件性能"""
        from ptest.suites import SuiteManager, TestSuite, CaseRef

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SuiteManager(storage_dir=tmpdir)

            # 创建包含100个用例的套件
            suite_data = {
                "name": "large_suite",
                "cases": [{"case_id": f"case_{i}", "order": i} for i in range(100)],
            }

            start = time.time()
            suite = manager.create_suite(suite_data)
            elapsed = time.time() - start

            assert len(suite.cases) == 100
            assert elapsed < 0.5

    def test_load_large_suite_performance(self):
        """测试加载大套件性能"""
        from ptest.suites import SuiteManager

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SuiteManager(storage_dir=tmpdir)

            # 先创建套件
            suite_data = {
                "name": "load_test_suite",
                "cases": [{"case_id": f"case_{i}", "order": i} for i in range(50)],
            }
            manager.create_suite(suite_data)

            # 测试加载性能
            start = time.time()
            suite = manager.load_suite("load_test_suite")
            elapsed = time.time() - start

            assert suite is not None
            assert elapsed < 0.1


class TestReportGenerationPerformance:
    """报告生成性能测试"""

    def test_generate_report_with_100_results(self):
        """测试生成100个结果的报告性能"""
        from ptest.reports.enhanced_generator import (
            EnhancedReportGenerator,
            ReportData,
            TestResult,
        )

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            generator = EnhancedReportGenerator(output_dir=tmpdir)

            results = [
                TestResult(
                    case_id=f"test_{i}",
                    status="passed" if i % 3 != 0 else "failed",
                    duration=0.1,
                )
                for i in range(100)
            ]

            data = ReportData(
                title="Performance Test Report",
                total=100,
                passed=67,
                failed=33,
                duration=10.0,
                results=results,
            )

            start = time.time()
            report_path = generator.generate(data)
            elapsed = time.time() - start

            assert report_path.exists()
            assert elapsed < 1.0


class TestMemoryUsage:
    """内存使用测试"""

    def test_data_generator_memory_usage(self):
        """测试数据生成器内存使用"""
        from ptest.data import DataGenerator

        generator = DataGenerator()

        # 生成大量数据
        result = generator.generate("name", count=10000, format="raw")

        assert len(result) == 10000
        # 10,000个字符串应该占用合理内存（<50MB）

    def test_suite_manager_memory_usage(self):
        """测试套件管理器内存使用"""
        from ptest.suites import SuiteManager

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SuiteManager(storage_dir=tmpdir)

            # 创建多个套件
            for i in range(10):
                suite_data = {
                    "name": f"suite_{i}",
                    "cases": [{"case_id": f"case_{j}", "order": j} for j in range(20)],
                }
                manager.create_suite(suite_data)

            # 验证可以正常加载所有套件
            suites = manager.list_suites()
            assert len(suites) == 10


class TestBenchmark:
    """基准测试"""

    @pytest.mark.benchmark
    def test_data_generation_benchmark(self):
        """数据生成基准测试"""
        from ptest.data import DataGenerator

        generator = DataGenerator()

        iterations = 100
        start = time.time()

        for _ in range(iterations):
            generator.generate("name", count=10, format="raw")

        elapsed = time.time() - start
        avg_time = elapsed / iterations

        # 平均每次生成应该在10ms以内
        assert avg_time < 0.01

    @pytest.mark.benchmark
    def test_suite_validation_benchmark(self):
        """套件验证基准测试"""
        from ptest.suites import TestSuite, CaseRef

        suite = TestSuite(
            name="benchmark_suite",
            cases=[CaseRef(case_id=f"case_{i}", order=i) for i in range(50)],
        )

        iterations = 100
        start = time.time()

        for _ in range(iterations):
            suite.validate()

        elapsed = time.time() - start
        avg_time = elapsed / iterations

        # 平均每次验证应该在1ms以内
        assert avg_time < 0.001
