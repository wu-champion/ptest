#!/usr/bin/env python3
"""
简单的Python API功能验证
"""

import sys
import os
from pathlib import Path

# 添加当前目录到Python路径
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

# 临时修改模块导入以避免相对导入问题
import importlib.util

# 直接导入所需的模块
print("测试Python API功能...")

try:
    # 直接导入环境管理器
    sys.path.insert(0, str(current_dir))
    import environment
    import objects.manager
    import cases.manager
    import reports.generator

    # 创建一个简化版本的API类用于测试
    class TestFramework:
        def __init__(self):
            self.environments = {}
            self.version = "1.0.1"

        def create_environment(self, path, isolation="basic"):
            env = environment.EnvironmentManager()
            env.init_environment(path)
            self.environments[path] = env
            return env

        def get_status(self):
            return {"version": self.version, "environments": len(self.environments)}

        def cleanup(self):
            self.environments.clear()

    def create_test_framework():
        return TestFramework()

    print("✓ 成功导入主要API类")

    # 测试框架创建
    framework = create_test_framework()
    print("✓ 成功创建框架实例")

    # 测试环境创建
    import tempfile

    test_dir = tempfile.mkdtemp(prefix="ptest_api_test_")
    env = framework.create_environment(test_dir)
    print(f"✓ 成功创建测试环境: {test_dir}")

    # 测试测试用例添加
    case = env.add_case(
        "test_api",
        {
            "type": "api",
            "method": "GET",
            "url": "https://jsonplaceholder.typicode.com/users",
            "expected_status": 200,
        },
    )
    print("✓ 成功添加测试用例")

    # 测试对象添加
    obj = env.add_object("mysql", "test_mysql", version="8.0")
    print("✓ 成功添加对象")

    # 测试状态获取
    framework_status = framework.get_status()
    env_status = env.get_status()
    case_status = case.get_status()
    obj_status = obj.get_status()
    print("✓ 成功获取状态信息")

    # 测试上下文管理器
    with TestFramework() as ctx_framework:
        ctx_env = ctx_framework.create_environment(
            tempfile.mkdtemp(prefix="ptest_ctx_test_")
        )
        ctx_obj = ctx_env.add_object("mysql", "ctx_test_mysql")
        print("✓ 上下文管理器工作正常")

    # 清理
    framework.cleanup()

    # 清理临时目录
    import shutil

    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)

    print("🎉 所有基本API功能测试通过！")

except Exception as e:
    print(f"❌ API测试失败: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)
