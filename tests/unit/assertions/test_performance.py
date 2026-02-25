import unittest
import sys
import time
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from ptest.assertions import AssertionFactory, AssertionResult  # noqa: E402


class TestAssertionPerformance(unittest.TestCase):
    """断言性能测试"""

    def test_single_assertion_performance(self):
        """单次断言应在 1ms 内完成"""
        eq = AssertionFactory.create("equal")

        times = []
        for _ in range(100):
            start = time.perf_counter()
            eq.assert_value(1, 1)
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)

        avg_ms = sum(times) / len(times)
        max_ms = max(times)

        print(f"\n单次断言性能: avg={avg_ms:.3f}ms, max={max_ms:.3f}ms")
        self.assertLess(avg_ms, 1.0, f"平均耗时 {avg_ms:.3f}ms 超过 1ms")

    def test_thousand_assertions_performance(self):
        """1000 次断言应在 100ms 内完成"""
        eq = AssertionFactory.create("equal")

        start = time.perf_counter()
        for i in range(1000):
            eq.assert_value(i, i)
        elapsed = (time.perf_counter() - start) * 1000

        print(f"\n1000次断言性能: {elapsed:.2f}ms")
        self.assertLess(elapsed, 100.0, f"1000次断言耗时 {elapsed:.2f}ms 超过 100ms")

    def test_various_assertions_performance(self):
        """各种断言类型性能测试"""
        assertions = [
            ("equal", AssertionFactory.create("equal"), (1, 1)),
            ("notequal", AssertionFactory.create("notequal"), (1, 2)),
            ("contains", AssertionFactory.create("contains"), ("hello world", "world")),
            ("truthy", AssertionFactory.create("truthy"), ("hello", None)),
            ("type", AssertionFactory.create("type"), ("hello", "str")),
            ("statuscode", AssertionFactory.create("statuscode"), (200, 200)),
        ]

        results = []
        for name, assertion, (actual, expected) in assertions:
            start = time.perf_counter()
            for _ in range(1000):
                assertion.assert_value(actual, expected)
            elapsed = (time.perf_counter() - start) * 1000
            results.append((name, elapsed))
            print(f"  {name}: {elapsed:.2f}ms")

        for name, elapsed in results:
            self.assertLess(
                elapsed, 100.0, f"{name} 1000次耗时 {elapsed:.2f}ms 超过 100ms"
            )

    def test_assertion_result_creation_performance(self):
        """AssertionResult 创建性能"""
        start = time.perf_counter()
        for i in range(10000):
            AssertionResult(passed=True, actual=i, expected=i)
        elapsed = (time.perf_counter() - start) * 1000

        print(f"\n10000次 Result 创建: {elapsed:.2f}ms")
        self.assertLess(elapsed, 500.0)

    def test_factory_create_performance(self):
        """工厂创建性能"""
        start = time.perf_counter()
        for _ in range(1000):
            AssertionFactory.create("equal")
        elapsed = (time.perf_counter() - start) * 1000

        print(f"\n1000次 Factory.create: {elapsed:.2f}ms")
        self.assertLess(elapsed, 200.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
