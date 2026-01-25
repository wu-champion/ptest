"""
ptest - 综合测试框架

一个完整的测试框架，用于管理测试环境、被测对象、测试用例和测试报告的完整生命周期。

基本使用:
    from ptest import TestFramework, create_test_framework

    # 创建框架实例
    framework = create_test_framework()

    # 创建测试环境
    env = framework.create_environment("/path/to/test")

    # 添加被测对象
    mysql = env.add_object("mysql", "my_db", version="8.0")

    # 添加测试用例
    case = env.add_case("api_test", {
        "type": "api",
        "endpoint": "/api/users",
        "method": "GET",
        "assertions": [{"status_code": 200}]
    })

    # 运行测试
    result = case.run()

    # 生成报告
    report_path = framework.generate_report("html")
"""

__version__ = "1.0.1"

# 导入主要的API类
from .api import (
    TestFramework,
    TestEnvironment,
    ManagedObject,
    TestCase,
    TestResult,
    create_test_framework,
    quick_test,
    PTestFramework,  # 向后兼容
)

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
