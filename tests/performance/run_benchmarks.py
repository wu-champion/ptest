#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
大规模性能基准测试脚本 / Large-Scale Performance Benchmark Script

按照 BENCHMARK_PLAN.md 执行性能测试
"""

import json
import sys
import time
import tracemalloc
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class BenchmarkReporter:
    """基准测试报告生成器"""

    def __init__(self, output_dir: str = "benchmark_results"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.results: Dict[str, List[Dict]] = {}

    def add_result(
        self,
        category: str,
        name: str,
        value: float,
        unit: str = "s",
        status: str = "pass",
        details: Optional[Dict] = None,
    ):
        """添加测试结果"""
        if category not in self.results:
            self.results[category] = []

        result = {
            "name": name,
            "value": value,
            "unit": unit,
            "status": status,
            "timestamp": datetime.now().isoformat(),
        }
        if details:
            result["details"] = details

        self.results[category].append(result)

    def generate_report(self) -> Dict[str, Any]:
        """生成报告"""
        import platform

        return {
            "metadata": {
                "version": "1.1.0",
                "timestamp": datetime.now().isoformat(),
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                "processor": platform.processor(),
            },
            "results": self.results,
            "summary": self._calculate_summary(),
        }

    def _calculate_summary(self) -> Dict[str, Any]:
        """计算摘要统计"""
        summary = {}
        for category, tests in self.results.items():
            values = [t["value"] for t in tests if t.get("status") == "pass"]
            failed = len([t for t in tests if t.get("status") == "fail"])

            summary[category] = {
                "count": len(tests),
                "passed": len(tests) - failed,
                "failed": failed,
                "total": sum(values) if values else 0,
                "avg": sum(values) / len(values) if values else 0,
                "min": min(values) if values else 0,
                "max": max(values) if values else 0,
            }
        return summary

    def save_json(self, filename: Optional[str] = None) -> Path:
        """保存 JSON 报告"""
        if filename is None:
            filename = f"benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        filepath = self.output_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.generate_report(), f, indent=2, ensure_ascii=False)

        print(f"📊 JSON 报告已保存: {filepath}")
        return filepath

    def save_markdown(self, filename: Optional[str] = None) -> Path:
        """保存 Markdown 报告"""
        if filename is None:
            filename = f"benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

        filepath = self.output_dir / filename
        report = self.generate_report()

        md = []
        md.append("# Performance Benchmark Report")
        md.append(f"\n**Version**: {report['metadata']['version']}")
        md.append(f"**Date**: {report['metadata']['timestamp']}")
        md.append(f"**Python**: {report['metadata']['python_version']}")
        md.append(f"**Platform**: {report['metadata']['platform']}")
        md.append("\n---\n")

        # 摘要
        md.append("## 📊 Summary\n")
        for category, stats in report["summary"].items():
            md.append(f"### {category}")
            md.append(
                f"- Tests: {stats['count']} (✓ {stats['passed']}, ✗ {stats['failed']})"
            )
            md.append(f"- Total: {stats['total']:.4f}s")
            md.append(f"- Average: {stats['avg']:.4f}s")
            md.append(f"- Min: {stats['min']:.4f}s")
            md.append(f"- Max: {stats['max']:.4f}s")
            md.append("")

        # 详细结果
        md.append("\n## 📈 Detailed Results\n")
        for category, tests in report["results"].items():
            md.append(f"### {category}\n")
            md.append("| Test | Value | Unit | Status |")
            md.append("|------|-------|------|--------|")
            for test in tests:
                status_icon = "✓" if test.get("status") == "pass" else "✗"
                md.append(
                    f"| {test['name']} | {test['value']:.4f} | {test['unit']} | {status_icon} |"
                )
            md.append("")

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(md))

        print(f"📝 Markdown 报告已保存: {filepath}")
        return filepath


def measure_memory_and_time(func, *args, **kwargs) -> Tuple[Any, float, float]:
    """测量函数执行时间和内存使用"""
    tracemalloc.start()
    start_time = time.time()

    result = func(*args, **kwargs)

    elapsed = time.time() - start_time
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # 转换为 MB
    peak_mb = peak / 1024 / 1024

    return result, elapsed, peak_mb


def generate_large_data(
    generator, data_type: str, total_count: int, batch_size: int = 10000
):
    """分批生成大规模数据（支持超过单次 MAX_GENERATION_COUNT 限制的数据生成）"""
    import tracemalloc

    tracemalloc.start()
    start_time = time.time()

    total_generated = 0
    num_batches = (total_count + batch_size - 1) // batch_size

    for i in range(num_batches):
        current_batch_size = min(batch_size, total_count - total_generated)
        if current_batch_size <= 0:
            break
        batch = generator.generate(data_type, count=current_batch_size, format="raw")
        total_generated += len(batch)
        # 不保存结果，仅测试生成速度

    elapsed = time.time() - start_time
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return total_generated, elapsed, peak / 1024 / 1024


def run_data_generation_benchmark(reporter: BenchmarkReporter):
    """数据生成性能测试 - 大规模"""
    print("\n🔧 Running Data Generation Benchmarks...")

    from ptest.data import DataGenerator

    generator = DataGenerator()

    # 基准测试: 1,000 条
    print("  测试 1,000 条数据生成 (基准)...")
    start = time.time()
    result = generator.generate("name", count=1000, format="raw")
    elapsed = time.time() - start
    reporter.add_result("Data Generation (1K)", "Generate 1K Names", elapsed)
    print(f"    ✓ Generate 1,000 names: {elapsed:.4f}s ({len(result)} items)")

    # 标准测试: 10,000 条
    print("  测试 10,000 条数据生成 (标准)...")
    start = time.time()
    result = generator.generate("email", count=10000, format="raw")
    elapsed = time.time() - start
    status = "pass" if elapsed < 1.0 else "fail"
    reporter.add_result(
        "Data Generation (10K)",
        "Generate 10K Emails",
        elapsed,
        status=status,
        details={"target": "< 1.0s"},
    )
    print(
        f"    {'✓' if status == 'pass' else '✗'} Generate 10,000 emails: {elapsed:.4f}s"
    )

    # 标准测试: 100,000 条
    print("  测试 100,000 条数据生成 (标准)...")
    start = time.time()
    result = generator.generate("name", count=100000, format="raw")
    elapsed = time.time() - start
    status = "pass" if elapsed < 3.0 else "fail"
    reporter.add_result(
        "Data Generation (100K)",
        "Generate 100K Names",
        elapsed,
        status=status,
        details={"target": "< 3.0s", "count": len(result)},
    )
    print(
        f"    {'✓' if status == 'pass' else '✗'} Generate 100,000 names: {elapsed:.4f}s (target: < 3s)"
    )

    # 压力测试: 1,000,000 条 (分批生成)
    print("  测试 1,000,000 条数据生成 (压力 - 分批处理)...")
    total_generated, elapsed, peak_mb = generate_large_data(generator, "uuid", 1000000)
    status = "pass" if elapsed < 60.0 and peak_mb < 2000 else "fail"
    reporter.add_result(
        "Data Generation (1M)",
        "Generate 1M UUIDs (batched)",
        elapsed,
        status=status,
        details={
            "total_generated": total_generated,
            "memory_mb": peak_mb,
            "target": "< 60s",
        },
    )
    print(
        f"    {'✓' if status == 'pass' else '✗'} Generate 1,000,000 UUIDs: {elapsed:.4f}s, Memory: {peak_mb:.2f}MB"
    )


def run_suite_management_benchmark(reporter: BenchmarkReporter):
    """套件管理性能测试 - 大规模"""
    print("\n📦 Running Suite Management Benchmarks...")

    from ptest.suites import SuiteManager, TestSuite, CaseRef

    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        manager = SuiteManager(storage_dir=tmpdir)

        # 测试 1: 100 个用例
        print("  测试 100 个用例套件...")
        suite_data = {
            "name": "suite_100",
            "cases": [{"case_id": f"case_{i}", "order": i} for i in range(100)],
        }

        start = time.time()
        suite = manager.create_suite(suite_data)
        elapsed = time.time() - start
        reporter.add_result(
            "Suite Management (100)", "Create Suite (100 cases)", elapsed
        )
        print(f"    ✓ Create suite with 100 cases: {elapsed:.4f}s")

        # 测试 2: 1,000 个用例
        print("  测试 1,000 个用例套件...")
        suite_data = {
            "name": "suite_1k",
            "cases": [{"case_id": f"case_{i}", "order": i} for i in range(1000)],
        }

        start = time.time()
        suite = manager.create_suite(suite_data)
        elapsed = time.time() - start
        status = "pass" if elapsed < 1.0 else "fail"
        reporter.add_result(
            "Suite Management (1K)",
            "Create Suite (1K cases)",
            elapsed,
            status=status,
            details={"target": "< 1.0s"},
        )
        print(
            f"    {'✓' if status == 'pass' else '✗'} Create suite with 1,000 cases: {elapsed:.4f}s"
        )

        # 测试 3: 1,000 个用例带依赖
        print("  测试 1,000 个用例带依赖 (链式依赖)...")
        cases = []
        for i in range(1000):
            case = {"case_id": f"case_dep_{i}", "order": i}
            if i > 0 and i % 10 == 0:  # 每 10 个一组依赖
                case["depends_on"] = [f"case_dep_{i - 1}"]
            cases.append(case)

        suite_data = {"name": "suite_1k_dep", "cases": cases}

        start = time.time()
        suite = manager.create_suite(suite_data)
        elapsed = time.time() - start
        status = "pass" if elapsed < 2.0 else "fail"
        reporter.add_result(
            "Suite Management (1K with deps)",
            "Create Suite (1K with dependencies)",
            elapsed,
            status=status,
            details={"target": "< 2.0s"},
        )
        print(
            f"    {'✓' if status == 'pass' else '✗'} Create suite with 1,000 cases (with deps): {elapsed:.4f}s"
        )

        # 测试 4: 拓扑排序性能
        print("  测试拓扑排序性能 (1,000 个用例)...")
        suite = TestSuite(
            name="topo_test",
            cases=[CaseRef(case_id=f"case_{i}", order=i) for i in range(1000)],
        )

        start = time.time()
        for _ in range(100):  # 执行 100 次取平均
            suite.validate()
        elapsed = (time.time() - start) / 100
        status = "pass" if elapsed < 0.01 else "fail"
        reporter.add_result(
            "Suite Management (Topology)",
            "Validate Suite (1K cases avg)",
            elapsed,
            status=status,
            details={"target": "< 0.01s", "iterations": 100},
        )
        print(
            f"    {'✓' if status == 'pass' else '✗'} Validate suite (avg of 100): {elapsed:.4f}s"
        )

        # 实际工程场景测试
        print("\n  📂 实际工程场景测试...")

        # TEST-SM-005: 高密度用例脚本（100 Cases/文件）
        print("    TEST-SM-005: 高密度用例脚本 (100 Cases/文件)...")
        suite_data = {
            "name": "high_density_100",
            "cases": [
                {"case_id": f"test_method_{i:03d}", "order": i} for i in range(100)
            ],
        }
        start = time.time()
        suite = manager.create_suite(suite_data)
        elapsed = time.time() - start
        status = "pass" if elapsed < 0.5 else "fail"
        reporter.add_result(
            "Suite Management (Real-world)",
            "High Density Script (100 Cases/file)",
            elapsed,
            status=status,
            details={
                "target": "< 0.5s",
                "scenario": "Python file with 100 test methods",
            },
        )
        print(
            f"      {'✓' if status == 'pass' else '✗'} 100 cases script: {elapsed:.4f}s"
        )

        # TEST-SM-006: 大型集成测试脚本（500 Cases/文件）
        print("    TEST-SM-006: 大型集成测试脚本 (500 Cases/文件)...")
        suite_data = {
            "name": "integration_test_500",
            "cases": [
                {"case_id": f"integration_step_{i:03d}", "order": i} for i in range(500)
            ],
        }
        start = time.time()
        suite = manager.create_suite(suite_data)
        elapsed = time.time() - start
        status = "pass" if elapsed < 2.0 else "fail"
        reporter.add_result(
            "Suite Management (Real-world)",
            "Integration Test Script (500 Cases/file)",
            elapsed,
            status=status,
            details={"target": "< 2.0s", "scenario": "Complex business flow test"},
        )
        print(
            f"      {'✓' if status == 'pass' else '✗'} 500 cases script: {elapsed:.4f}s"
        )

        # TEST-SM-007: SQL批量验证脚本（1000 SQL/文件）
        print("    TEST-SM-007: SQL批量验证脚本 (1000 SQL/文件)...")
        suite_data = {
            "name": "sql_batch_1000",
            "cases": [
                {"case_id": f"sql_validation_{i:04d}", "order": i} for i in range(1000)
            ],
        }
        start = time.time()
        suite = manager.create_suite(suite_data)
        elapsed = time.time() - start
        status = "pass" if elapsed < 3.0 else "fail"
        reporter.add_result(
            "Suite Management (Real-world)",
            "SQL Batch Script (1000 SQL/file)",
            elapsed,
            status=status,
            details={"target": "< 3.0s", "scenario": "Database validation script"},
        )
        print(
            f"      {'✓' if status == 'pass' else '✗'} 1000 SQL script: {elapsed:.4f}s"
        )

        # TEST-SM-008: 版本迭代用例冗余模拟
        print("    TEST-SM-008: 版本迭代用例冗余模拟...")
        cases = []
        # v1.0: 功能A（100 Cases）
        for i in range(100):
            cases.append({"case_id": f"v1_feature_A_{i:03d}", "order": len(cases)})
        # v2.0: 功能B依赖A（100 Cases，其中30个重复测试A）
        for i in range(100):
            case = {"case_id": f"v2_feature_B_{i:03d}", "order": len(cases)}
            if i < 30:  # 30个重复测试A
                case["depends_on"] = [f"v1_feature_A_{i:03d}"]
            cases.append(case)
        # v3.0: 功能C依赖A+B（100 Cases，其中50个重复测试）
        for i in range(100):
            case = {"case_id": f"v3_feature_C_{i:03d}", "order": len(cases)}
            if i < 25:  # 25个重复测试A
                case["depends_on"] = [f"v1_feature_A_{i:03d}"]
            elif i < 50:  # 25个重复测试B
                case["depends_on"] = [f"v2_feature_B_{i - 25:03d}"]
            cases.append(case)

        suite_data = {"name": "version_iteration_redundancy", "cases": cases}
        start = time.time()
        suite = manager.create_suite(suite_data)
        elapsed = time.time() - start
        status = "pass" if elapsed < 3.0 else "fail"
        reporter.add_result(
            "Suite Management (Real-world)",
            "Version Iteration Redundancy (300 Cases)",
            elapsed,
            status=status,
            details={
                "target": "< 3.0s",
                "scenario": "Multi-version with redundant cases",
                "total_cases": 300,
                "effective_coverage": "~200",
            },
        )
        print(
            f"      {'✓' if status == 'pass' else '✗'} Version iteration (300 cases): {elapsed:.4f}s"
        )


def run_parallel_execution_benchmark(reporter: BenchmarkReporter):
    """并行执行性能测试 - 大规模"""
    print("\n⚡ Running Parallel Execution Benchmarks...")

    from ptest.execution import ExecutionTask, ParallelExecutor, SequentialExecutor

    def task_func(duration: float = 0.01) -> str:
        """模拟测试用例执行"""
        time.sleep(duration)
        return "done"

    # 测试 1: 10 个任务串行
    print("  测试 10 个任务串行...")
    tasks = [
        ExecutionTask(task_id=f"task_{i}", func=lambda: task_func(0.01))
        for i in range(10)
    ]

    sequential = SequentialExecutor()
    start = time.time()
    sequential.execute(tasks)
    seq_time_10 = time.time() - start
    reporter.add_result("Execution (10)", "Sequential (10 tasks)", seq_time_10)
    print(f"    ✓ Sequential (10 tasks): {seq_time_10:.4f}s")

    # 测试 2: 10 个任务并行
    print("  测试 10 个任务并行...")
    tasks = [
        ExecutionTask(task_id=f"task_{i}", func=lambda: task_func(0.01))
        for i in range(10)
    ]

    parallel = ParallelExecutor(max_workers=4)
    start = time.time()
    parallel.execute(tasks)
    par_time_10 = time.time() - start
    parallel.shutdown()

    speedup_10 = seq_time_10 / par_time_10 if par_time_10 > 0 else 0
    status = "pass" if speedup_10 > 1.5 else "fail"
    reporter.add_result(
        "Execution (10)",
        "Parallel (10 tasks)",
        par_time_10,
        status=status,
        details={"speedup": speedup_10, "target_speedup": "> 1.5x"},
    )
    print(
        f"    {'✓' if status == 'pass' else '✗'} Parallel (10 tasks): {par_time_10:.4f}s (Speedup: {speedup_10:.2f}x)"
    )

    # 测试 3: 100 个任务串行
    print("  测试 100 个任务串行...")
    tasks = [
        ExecutionTask(task_id=f"task_{i}", func=lambda: task_func(0.05))
        for i in range(100)
    ]

    sequential = SequentialExecutor()
    start = time.time()
    sequential.execute(tasks)
    seq_time_100 = time.time() - start
    reporter.add_result("Execution (100)", "Sequential (100 tasks)", seq_time_100)
    print(f"    ✓ Sequential (100 tasks): {seq_time_100:.4f}s")

    # 测试 4: 100 个任务并行
    print("  测试 100 个任务并行 (4 workers)...")
    tasks = [
        ExecutionTask(task_id=f"task_{i}", func=lambda: task_func(0.05))
        for i in range(100)
    ]

    parallel = ParallelExecutor(max_workers=4)
    start = time.time()
    parallel.execute(tasks)
    par_time_100 = time.time() - start
    parallel.shutdown()

    speedup_100 = seq_time_100 / par_time_100 if par_time_100 > 0 else 0
    status = "pass" if speedup_100 > 2.0 and par_time_100 < 30 else "fail"
    reporter.add_result(
        "Execution (100)",
        "Parallel (100 tasks, 4 workers)",
        par_time_100,
        status=status,
        details={
            "speedup": speedup_100,
            "target_time": "< 30s",
            "target_speedup": "> 2x",
        },
    )
    print(
        f"    {'✓' if status == 'pass' else '✗'} Parallel (100 tasks): {par_time_100:.4f}s (Speedup: {speedup_100:.2f}x)"
    )


def run_report_generation_benchmark(reporter: BenchmarkReporter):
    """报告生成性能测试 - 大规模"""
    print("\n📊 Running Report Generation Benchmarks...")

    from ptest.reports.enhanced_generator import (
        EnhancedReportGenerator,
        ReportData,
        TestResult,
    )

    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        generator = EnhancedReportGenerator(output_dir=tmpdir)

        # 测试 1: 100 个结果
        print("  测试 100 个结果报告...")
        results = [
            TestResult(
                case_id=f"test_{i}",
                status="passed" if i % 3 != 0 else "failed",
                duration=0.1,
            )
            for i in range(100)
        ]

        data = ReportData(
            title="Benchmark Report (100)",
            total=100,
            passed=67,
            failed=33,
            duration=10.0,
            results=results,
        )

        start = time.time()
        report_path = generator.generate(data)
        elapsed = time.time() - start
        reporter.add_result(
            "Report Generation (100)", "Generate Report (100 results)", elapsed
        )
        print(
            f"    ✓ Generate report (100 results): {elapsed:.4f}s -> {report_path.name}"
        )

        # 测试 2: 1,000 个结果
        print("  测试 1,000 个结果报告...")
        results = [
            TestResult(
                case_id=f"test_{i}",
                status="passed" if i % 5 != 0 else "failed",
                duration=0.1,
            )
            for i in range(1000)
        ]

        data = ReportData(
            title="Benchmark Report (1K)",
            total=1000,
            passed=800,
            failed=200,
            duration=100.0,
            results=results,
        )

        result, elapsed, peak_mb = measure_memory_and_time(generator.generate, data)
        status = "pass" if elapsed < 2.0 and peak_mb < 500 else "fail"
        reporter.add_result(
            "Report Generation (1K)",
            "Generate Report (1K results)",
            elapsed,
            status=status,
            details={
                "memory_mb": peak_mb,
                "target_time": "< 2s",
                "target_memory": "< 500MB",
            },
        )
        print(
            f"    {'✓' if status == 'pass' else '✗'} Generate report (1,000 results): {elapsed:.4f}s, Memory: {peak_mb:.2f}MB"
        )


def run_isolation_engine_benchmark(reporter: BenchmarkReporter):
    """隔离引擎性能测试"""
    print("\n🔒 Running Isolation Engine Benchmarks...")

    from ptest.isolation import IsolationManager

    manager = IsolationManager()

    # 运行引擎基准测试
    print("  运行引擎基准测试 (creation, activation, command_exec)...")
    results = manager.benchmark_engines(
        test_scenarios=["creation", "activation", "command_exec"]
    )

    for level, data in results.items():
        print(f"\n  Engine: {level}")
        benchmarks = data.get("benchmarks", {})

        if "creation_time" in benchmarks:
            target = {"basic": 1.0, "virtualenv": 5.0, "docker": 10.0}.get(level, 5.0)
            status = "pass" if benchmarks["creation_time"] < target else "fail"
            reporter.add_result(
                f"Isolation ({level})",
                "Environment Creation",
                benchmarks["creation_time"],
                status=status,
                details={"target": f"< {target}s"},
            )
            print(
                f"    {'✓' if status == 'pass' else '✗'} Creation: {benchmarks['creation_time']:.4f}s (target: < {target}s)"
            )

        if "activation_time" in benchmarks:
            reporter.add_result(
                f"Isolation ({level})",
                "Environment Activation",
                benchmarks["activation_time"],
            )
            print(f"    ✓ Activation: {benchmarks['activation_time']:.4f}s")

        if "command_exec_time" in benchmarks:
            reporter.add_result(
                f"Isolation ({level})",
                "Command Execution",
                benchmarks["command_exec_time"],
            )
            print(f"    ✓ Command exec: {benchmarks['command_exec_time']:.4f}s")


def run_all_benchmarks():
    """运行所有基准测试"""
    print("=" * 70)
    print("🚀 ptestx Large-Scale Performance Benchmark Suite")
    print("=" * 70)
    print("\n测试级别:")
    print("  • 基准级: 1,000 数据 / 100 用例")
    print("  • 标准级: 100,000 数据 / 1,000 用例")
    print("  • 压力级: 1,000,000 数据 / 大规模并发")
    print()

    reporter = BenchmarkReporter()

    try:
        # 运行各类基准测试
        run_data_generation_benchmark(reporter)
        run_suite_management_benchmark(reporter)
        run_parallel_execution_benchmark(reporter)
        run_report_generation_benchmark(reporter)
        run_isolation_engine_benchmark(reporter)

        # 生成报告
        print("\n" + "=" * 70)
        print("📊 Generating Reports...")
        print("=" * 70)

        json_path = reporter.save_json()
        md_path = reporter.save_markdown()

        # 打印摘要
        print("\n📈 Summary:")
        report = reporter.generate_report()
        total_tests = 0
        total_passed = 0
        total_failed = 0

        for category, stats in report["summary"].items():
            total_tests += stats["count"]
            total_passed += stats["passed"]
            total_failed += stats["failed"]
            print(f"  {category}:")
            print(
                f"    - Tests: {stats['count']} (✓ {stats['passed']}, ✗ {stats['failed']})"
            )
            if stats["count"] > 0:
                print(f"    - Total: {stats['total']:.4f}s")
                print(f"    - Average: {stats['avg']:.4f}s")

        print(f"\n{'=' * 70}")
        print(f"✅ All benchmarks completed!")
        print(f"   Total: {total_tests} tests (✓ {total_passed}, ✗ {total_failed})")
        print(f"📁 Results saved to: {reporter.output_dir}")
        print(f"📊 JSON: {json_path.name}")
        print(f"📝 Markdown: {md_path.name}")
        print("=" * 70)

        return 0 if total_failed == 0 else 1

    except Exception as e:
        print(f"\n❌ Benchmark failed: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(run_all_benchmarks())
