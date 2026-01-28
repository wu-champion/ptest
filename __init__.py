"""
ptest - 综合测试框架

一个完整的测试框架，用于管理测试环境、被测对象、测试用例和测试报告的完整生命周期。
"""

__version__ = "1.0.1"

# 临时简化导入，确保基础导入工作
__all__ = ["__version__"]

# 导入便捷函数
__all__ = [
    # 版本信息
    "__version__",
    # 主要API类
    "TestFramework",
    "TestEnvironment",
    "ManagedObject",
    "TestCase",
    "TestResult",
    # 便捷函数
    "create_test_framework",
    "quick_test",
    # 向后兼容
    "PTestFramework",
]

# 设置默认导出
default_export = "TestFramework"
