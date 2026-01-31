"""
Docker隔离引擎简单测试

快速验证Docker引擎的基本功能
"""

import sys
import tempfile
from pathlib import Path


def test_docker_engine_basic_functionality():
    """测试Docker引擎基本功能"""
    print("开始测试Docker引擎基本功能...")

    try:
        # 导入模块
        from ptest.isolation.docker_engine import (
            DockerIsolationEngine,
            DockerEnvironment,
        )
        from ptest.isolation.enums import EnvironmentStatus

        print("✓ 成功导入模块")

        # 创建引擎
        engine = DockerIsolationEngine(
            {
                "container_timeout": 30,
                "simulation_mode": True,  # 启用模拟模式
            }
        )
        print("✓ 成功创建Docker引擎")

        # 测试引擎信息
        engine_info = engine.get_engine_info()
        print(f"✓ 引擎类型: {engine_info.get('engine_type')}")
        print(f"✓ Docker可用: {engine_info.get('docker_available')}")

        # 测试支持的功能
        features = engine.get_supported_features()
        print(f"✓ 支持的功能: {features}")

        # 创建临时目录
        temp_dir = Path(tempfile.mkdtemp())
        print(f"✓ 创建临时目录: {temp_dir}")

        try:
            # 创建Docker环境
            env_id = "test_docker_env"
            env = DockerEnvironment(
                env_id,
                temp_dir,
                engine,
                {
                    "image": "python:3.9-slim",
                    "simulation_mode": True,
                },
            )
            print("✓ 成功创建DockerEnvironment")

            # 测试环境属性
            print(f"✓ 容器名称: {env.container_name}")
            print(f"✓ 镜像名称: {env.image_name}")

            # 测试端口分配
            port = env.allocate_port()
            print(f"✓ 端口分配: {port}")

            # 测试端口释放
            released = env.release_port(port)
            print(f"✓ 端口释放: {released}")

            # 模拟环境创建
            created = env.create_container()
            print(f"✓ 容器创建: {created}")

            if created:
                # 模拟容器启动
                started = env.start_container()
                print(f"✓ 容器启动: {started}")

                if started:
                    # 模拟命令执行
                    result = env.execute_command(["python", "--version"])
                    print(f"✓ 命令执行: {result.success}")
                    if result.success:
                        print(f"  输出: {result.stdout.strip()}")

                    # 模拟容器停止
                    stopped = env.stop_container()
                    print(f"✓ 容器停止: {stopped}")

                # 模拟容器删除
                removed = env.remove_container()
                print(f"✓ 容器删除: {removed}")

            # 测试状态查询
            status = engine.get_isolation_status(env_id)
            print(f"✓ 状态查询: {status.get('isolation_type')}")

            # 测试引擎状态
            docker_status = engine.verify_docker_environment()
            print(f"✓ Docker环境验证: {docker_status.get('available', 'simulation')}")

        finally:
            # 清理临时目录
            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)
            print("✓ 清理临时目录")

        print("✓ 基本功能测试完成")
        return True

    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_docker_environment_methods():
    """测试Docker环境方法"""
    print("\n开始测试Docker环境方法...")

    try:
        from isolation.docker_engine import DockerIsolationEngine, DockerEnvironment

        # 创建引擎
        engine = DockerIsolationEngine({})

        # 创建临时目录
        temp_dir = Path(tempfile.mkdtemp())
        try:
            # 创建环境
            env = DockerEnvironment("test_methods", temp_dir, engine, {})

            # 测试容器信息获取
            container_info = env.get_container_info()
            print(f"✓ 容器信息: {container_info.get('status', 'simulated')}")

            # 测试包管理相关方法
            packages = env.get_installed_packages()
            print(f"✓ 已安装包查询: {len(packages)} 个包")

            version = env.get_package_version("requests")
            print(f"✓ 包版本查询: {version or 'None'}")

            # 测试包安装（模拟）
            installed = env.install_package("requests==2.28.1")
            print(f"✓ 包安装: {installed}")

            # 测试包卸载（模拟）
            uninstalled = env.uninstall_package("requests")
            print(f"✓ 包卸载: {uninstalled}")

            # 测试隔离验证
            is_valid = env.validate_isolation()
            print(f"✓ 隔离验证: {is_valid}")

            # 测试环境清理
            cleaned = env.cleanup()
            print(f"✓ 环境清理: {cleaned}")

        finally:
            # 清理临时目录
            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)

        print("✓ 环境方法测试完成")
        return True

    except Exception as e:
        print(f"✗ 环境方法测试失败: {e}")
        return False


def test_docker_engine_advanced_features():
    """测试Docker引擎高级功能"""
    print("\n开始测试Docker引擎高级功能...")

    try:
        from isolation.docker_engine import DockerIsolationEngine

        # 创建引擎
        engine = DockerIsolationEngine({})

        # 测试镜像列表
        images = engine.list_available_images()
        print(f"✓ 可用镜像: {len(images)} 个")

        # 测试镜像拉取（模拟）
        pulled = engine.pull_image("python:3.9-slim")
        print(f"✓ 镜像拉取: {pulled}")

        # 测试网络创建（模拟）
        network = engine.create_network("test_network", "172.20.0.0/16")
        print(f"✓ 网络创建: {network is not None}")

        # 测试卷创建（模拟）
        volume = engine.create_volume("test_volume")
        print(f"✓ 卷创建: {volume is not None}")

        # 测试资源清理（模拟）
        cleanup_counts = engine.cleanup_unused_resources()
        print(f"✓ 资源清理: {cleanup_counts}")

        print("✓ 高级功能测试完成")
        return True

    except Exception as e:
        print(f"✗ 高级功能测试失败: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("Docker隔离引擎测试")
    print("注意: 由于Docker环境限制，本测试在模拟模式下运行")
    print("=" * 60)

    success1 = test_docker_engine_basic_functionality()
    success2 = test_docker_environment_methods()
    success3 = test_docker_engine_advanced_features()

    print("\n" + "=" * 60)
    if success1 and success2 and success3:
        print("✓ 所有测试通过!")
        sys.exit(0)
    else:
        print("✗ 部分测试失败")
        sys.exit(1)
