"""
ptest - 综合测试框架

一个完整的测试框架，用于管理测试环境、被测对象、测试用例和测试报告的完整生命周期。
"""

__version__ = "1.3.0"

# 导入核心组件
from .core import get_logger
from .config import DEFAULT_CONFIG

# 导入便捷函数
__all__ = [
    "__version__",
    "get_logger",
    "DEFAULT_CONFIG",
]
