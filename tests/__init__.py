# ptest/tests/__init__.py
"""
ptest 测试模块

提供完整的测试套件，包括单元测试、集成测试、端到端测试、性能测试和验证测试。
"""

# 导入路径配置
import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 测试版本
__version__ = "1.0.0"

# 测试配置
DEFAULT_TEST_CONFIG = {
    "timeout": 300,
    "verbose": False,
    "coverage": False,
    "parallel": False,
    "test_data_dir": project_root / "tests" / "data",
    "test_temp_dir": project_root / "tests" / "temp",
    "test_reports_dir": project_root / "tests" / "reports",
    "default_timeout": 30,
    "log_level": "INFO",
    "markers": [
        "unit: 单元测试",
        "integration: 集成测试",
        "e2e: 端到端测试",
        "performance: 性能测试",
        "verification: 验证测试",
        "slow: 慢速测试",
        "isolation: 环境隔离测试",
        "database: 数据库相关测试",
        "api: API相关测试",
        "core: 核心功能测试",
        "objects: 对象管理测试",
    ],
}

# 测试环境变量
TEST_ENV_VARS = {
    "PYTHONPATH": str(project_root),
    "PTEST_TEST_MODE": "true",
    "PTEST_TEST_TEMP_DIR": str(project_root / "tests" / "temp"),
    "PTEST_TEST_DATA_DIR": str(project_root / "tests" / "data"),
}

# 设置测试环境变量
for key, value in TEST_ENV_VARS.items():
    os.environ[key] = value

# 导入测试工具
try:
    import pytest  # noqa: F401

    HAS_PYTEST = True
except ImportError:
    HAS_PYTEST = False

try:
    import unittest  # noqa: F401

    HAS_UNITTEST = True
except ImportError:
    HAS_UNITTEST = False


# 确保测试目录存在
def ensure_test_dirs():
    """确保测试所需目录存在"""
    for dir_path in [
        DEFAULT_TEST_CONFIG["test_data_dir"],
        DEFAULT_TEST_CONFIG["test_temp_dir"],
        DEFAULT_TEST_CONFIG["test_reports_dir"],
    ]:
        dir_path.mkdir(parents=True, exist_ok=True)


# 自动创建测试目录
ensure_test_dirs()

# 导出配置和工具
__all__ = [
    "DEFAULT_TEST_CONFIG",
    "TEST_ENV_VARS",
    "HAS_PYTEST",
    "HAS_UNITTEST",
    "ensure_test_dirs",
    "DEFAULT_TEST_CONFIG",
]
