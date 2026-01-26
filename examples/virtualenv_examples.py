"""
Virtualenv隔离引擎使用示例

演示如何使用Virtualenv隔离引擎进行测试环境管理
"""

import sys
import tempfile
import shutil
from pathlib import Path

# 添加项目路径
current_dir = Path(__file__).parent.parent
sys.path.insert(0, str(current_dir))

from isolation.virtualenv_engine import VirtualenvIsolationEngine, VirtualenvEnvironment
from isolation.enums import IsolationEvent


def example_basic_usage():
    """基本使用示例"""
    print("=" * 60)
    print("Virtualenv隔离引擎基本使用示例")
    print("=" * 60)

    try:
        # 1. 创建引擎
        engine = VirtualenvIsolationEngine(
            {
                "command_timeout": 60,
                "pip_timeout": 120,
            }
        )
        print("✓ 创建Virtualenv隔离引擎")

        # 2. 创建环境
        temp_dir = Path(tempfile.mkdtemp())
        env_id = "example_env"

        try:
            # 创建隔离环境（跳过实际venv创建）
            env = VirtualenvEnvironment(env_id, temp_dir, engine, {})
            print(f"✓ 创建隔离环境: {env_id}")

            # 3. 配置环境
            config = {
                "project_name": "test_project",
                "description": "测试环境示例",
            }
            print(f"✓ 环境配置: {config}")

            # 4. 端口管理
            port1 = env.allocate_port()
            port2 = env.allocate_port()
            print(f"✓ 分配端口: {port1}, {port2}")

            # 5. 环境状态
            from isolation.enums import EnvironmentStatus

            env.status = EnvironmentStatus.ACTIVE
            status = env.get_status()
            print(f"✓ 环境状态: {status['status']}")

            # 6. 引擎信息
            engine_info = engine.get_engine_info()
            print(f"✓ 引擎类型: {engine_info['engine_type']}")
            print(f"✓ 支持功能: {engine_info['supported_features']}")

            # 7. 清理端口
            env.release_port(port1)
            env.release_port(port2)
            print("✓ 释放端口")

        finally:
            # 8. 清理
            shutil.rmtree(temp_dir, ignore_errors=True)
            print("✓ 清理临时目录")

        print("\n✓ 基本使用示例完成")
        return True

    except Exception as e:
        print(f"✗ 基本使用示例失败: {e}")
        return False


def example_error_handling():
    """错误处理示例"""
    print("\n" + "=" * 60)
    print("错误处理示例")
    print("=" * 60)

    try:
        engine = VirtualenvIsolationEngine({})

        # 测试无效环境查询
        status = engine.get_isolation_status("nonexistent_env")
        print(f"✓ 无效环境查询: {status['status']}")

        # 测试无效端口释放
        temp_dir = Path(tempfile.mkdtemp())
        try:
            env = VirtualenvEnvironment("test", temp_dir, engine, {})
            result = env.release_port(99999)  # 不存在的端口
            print(f"✓ 无效端口释放: {result}")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        print("\n✓ 错误处理示例完成")
        return True

    except Exception as e:
        print(f"✗ 错误处理示例失败: {e}")
        return False


def example_configuration():
    """配置示例"""
    print("\n" + "=" * 60)
    print("配置示例")
    print("=" * 60)

    try:
        # 不同配置的引擎
        configs = [
            {"name": "默认配置", "config": {}},
            {
                "name": "快速配置",
                "config": {
                    "command_timeout": 30,
                    "pip_timeout": 60,
                },
            },
            {
                "name": "安全配置",
                "config": {
                    "system_site_packages": False,
                    "clear": True,
                },
            },
        ]

        for item in configs:
            engine = VirtualenvIsolationEngine(item["config"])
            info = engine.get_engine_info()
            print(f"✓ {item['name']}:")
            print(f"  - 引擎类型: {info['engine_type']}")
            print(f"  - 配置项: {len(engine.engine_config)}")

        print("\n✓ 配置示例完成")
        return True

    except Exception as e:
        print(f"✗ 配置示例失败: {e}")
        return False


def example_event_system():
    """事件系统示例"""
    print("\n" + "=" * 60)
    print("事件系统示例")
    print("=" * 60)

    try:

        def event_handler(env, event, *args, **kwargs):
            print(f"  事件触发: {event.value} - 环境: {env.env_id}")

        # 创建环境和事件监听
        temp_dir = Path(tempfile.mkdtemp())
        try:
            engine = VirtualenvIsolationEngine({})
            env = VirtualenvEnvironment("event_test", temp_dir, engine, {})

            # 添加事件监听器
            env.add_event_listener(IsolationEvent.ENVIRONMENT_CREATED, event_handler)
            env.add_event_listener(IsolationEvent.ENVIRONMENT_ACTIVATED, event_handler)
            env.add_event_listener(IsolationEvent.PACKAGE_INSTALLED, event_handler)

            print("✓ 添加事件监听器")

            # 模拟事件触发（实际使用中这些会由系统自动触发）
            env._emit_event(IsolationEvent.ENVIRONMENT_CREATED)
            env._emit_event(IsolationEvent.ENVIRONMENT_ACTIVATED)
            env._emit_event(IsolationEvent.PACKAGE_INSTALLED, package="test_package")

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        print("\n✓ 事件系统示例完成")
        return True

    except Exception as e:
        print(f"✗ 事件系统示例失败: {e}")
        return False


def example_concurrent_environments():
    """并发环境示例"""
    print("\n" + "=" * 60)
    print("并发环境示例")
    print("=" * 60)

    try:
        import threading
        import time

        def create_environment(env_num):
            temp_dir = Path(tempfile.mkdtemp())
            try:
                engine = VirtualenvIsolationEngine({})
                env = VirtualenvEnvironment(
                    f"concurrent_{env_num}", temp_dir, engine, {}
                )

                # 模拟环境初始化
                time.sleep(0.1)
                env.status = "active"

                # 分配端口
                port = env.allocate_port()

                print(f"  线程 {env_num}: 环境 {env.env_id}, 端口 {port}")

                return env.env_id, port

            finally:
                time.sleep(0.05)
                shutil.rmtree(temp_dir, ignore_errors=True)

        # 创建多个线程
        threads = []
        for i in range(3):
            thread = threading.Thread(target=create_environment, args=(i + 1,))
            threads.append(thread)
            thread.start()

        # 等待所有线程完成
        for thread in threads:
            thread.join()

        print("\n✓ 并发环境示例完成")
        return True

    except Exception as e:
        print(f"✗ 并发环境示例失败: {e}")
        return False


def main():
    """主函数"""
    print("Virtualenv隔离引擎使用示例")
    print("注意: 由于系统限制，本示例跳过实际的venv创建")

    examples = [
        example_basic_usage,
        example_error_handling,
        example_configuration,
        example_event_system,
        example_concurrent_environments,
    ]

    results = []
    for example in examples:
        try:
            result = example()
            results.append(result)
        except Exception as e:
            print(f"示例执行异常: {e}")
            results.append(False)

    print("\n" + "=" * 60)
    print("总结")
    print("=" * 60)

    success_count = sum(results)
    total_count = len(results)

    print(f"成功示例: {success_count}/{total_count}")

    if success_count == total_count:
        print("🎉 所有示例都成功执行!")
        return 0
    else:
        print("⚠️  部分示例失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
