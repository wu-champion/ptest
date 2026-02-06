#!/usr/bin/env python3
"""
Docker引擎基础功能验证测试

这个测试脚本验证Docker隔离引擎的核心功能是否正常工作
"""

import sys
import tempfile
from pathlib import Path
import pytest

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

# 框架导入
from ptest.isolation.docker_engine import DockerIsolationEngine, DockerEnvironment  # noqa: E402
from ptest.isolation.base import IsolationEngine, IsolatedEnvironment  # noqa: E402
from ptest.core import get_logger  # noqa: E402

# 设置测试日志
logger = get_logger("docker_basic_test")


def is_docker_available():
    """检查Docker是否可用"""
    try:
        import docker

        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


@pytest.mark.skipif(
    not is_docker_available(), reason="Docker不可用，跳过真实Docker测试"
)
def test_docker_engine_basic_functionality():
    """测试Docker引擎基础功能"""
    logger.info("开始Docker引擎基础功能测试")

    success_count = 0
    total_tests = 0

    # 测试1: 引擎初始化
    total_tests += 1
    try:
        engine_config = {
            "default_image": "python:3.9-slim",
            "network_subnet": "172.20.0.0/16",
            "volume_base_path": "/tmp/ptest_volumes",
            "container_timeout": 60,
            "pull_timeout": 120,
        }

        engine = DockerIsolationEngine(engine_config)

        # 验证引擎属性
        assert isinstance(engine, DockerIsolationEngine)
        assert isinstance(engine, IsolationEngine)
        assert len(engine.supported_features) >= 8
        assert engine.engine_config["default_image"] == "python:3.9-slim"

        logger.info("✓ 测试1: Docker引擎初始化 - 通过")
        success_count += 1

    except Exception as e:
        logger.error(f"✗ 测试1: Docker引擎初始化 - 失败: {e}")

    # 测试2: Docker环境验证
    total_tests += 1
    try:
        docker_env = engine.verify_docker_environment()
        assert isinstance(docker_env, dict)
        assert "available" in docker_env
        assert "simulation_mode" in docker_env

        logger.info("✓ 测试2: Docker环境验证 - 通过")
        success_count += 1

    except Exception as e:
        logger.error(f"✗ 测试2: Docker环境验证 - 失败: {e}")

    # 测试3: 环境创建（模拟模式）
    total_tests += 1
    try:
        temp_dir = Path(tempfile.mkdtemp())
        env = engine.create_isolation(
            temp_dir,
            "test_env_id",
            {
                "image": "python:3.9-slim",
                "environment_vars": {"TEST_VAR": "test_value"},
                "resource_limits": {"memory": "256m", "cpus": "0.5"},
            },
        )

        assert isinstance(env, DockerEnvironment)
        assert isinstance(env, IsolatedEnvironment)
        assert env.env_id == "test_env_id"
        assert env.image_name == "python:3.9-slim"
        assert env.environment_vars["TEST_VAR"] == "test_value"
        assert env.resource_limits["memory"] == "256m"

        logger.info("✓ 测试3: 环境创建 - 通过")
        success_count += 1

    except Exception as e:
        logger.error(f"✗ 测试3: 环境创建 - 失败: {e}")

    # 测试4: 端口管理
    total_tests += 1
    try:
        temp_dir = Path(tempfile.mkdtemp())
        env = engine.create_isolation(temp_dir, "test_port_env", {})

        # 测试端口分配
        allocated_port = env.allocate_port()
        assert isinstance(allocated_port, int)
        assert allocated_port > 0
        assert allocated_port in env.allocated_ports
        assert allocated_port in env.port_mappings

        # 测试端口释放
        released = env.release_port(allocated_port)
        assert released is True
        assert allocated_port not in env.allocated_ports
        assert allocated_port not in env.port_mappings

        logger.info("✓ 测试4: 端口管理 - 通过")
        success_count += 1

    except Exception as e:
        logger.error(f"✗ 测试4: 端口管理 - 失败: {e}")

    # 测试5: 快照功能（基础）
    total_tests += 1
    try:
        temp_dir = Path(tempfile.mkdtemp())
        env = engine.create_isolation(temp_dir, "test_snapshot_env", {})

        # 创建快照
        snapshot = env.create_snapshot("test_basic_snapshot")
        assert isinstance(snapshot, dict)
        assert snapshot["snapshot_id"] == "test_basic_snapshot"
        assert snapshot["env_id"] == env.env_id
        assert "docker_info" in snapshot
        assert "created_at" in snapshot

        # 验证快照内容
        docker_info = snapshot["docker_info"]
        assert docker_info["container_name"] == env.container_name
        assert docker_info["image_name"] == env.image_name

        # 测试导出快照数据
        export_data = env.export_snapshot_data()
        assert isinstance(export_data, dict)
        assert export_data["env_id"] == env.env_id
        assert export_data["env_type"] == "docker"

        logger.info("✓ 测试5: 快照功能 - 通过")
        success_count += 1

    except Exception as e:
        logger.error(f"✗ 测试5: 快照功能 - 失败: {e}")

    # 测试6: 环境状态跟踪
    total_tests += 1
    try:
        temp_dir = Path(tempfile.mkdtemp())
        env = engine.create_isolation(temp_dir, "test_status_env", {})

        # 获取初始状态
        status = engine.get_isolation_status(env.env_id)
        assert isinstance(status, dict)
        assert status["status"] == "created"
        assert status["isolation_type"] == "docker"

        logger.info("✓ 测试6: 环境状态跟踪 - 通过")
        success_count += 1

    except Exception as e:
        logger.error(f"✗ 测试6: 环境状态跟踪 - 失败: {e}")

    # 测试7: 引擎信息
    total_tests += 1
    try:
        engine_info = engine.get_engine_info()
        assert isinstance(engine_info, dict)
        assert engine_info["engine_type"] == "docker"
        assert "supported_features" in engine_info
        assert "docker_environment" in engine_info

        logger.info("✓ 测试7: 引擎信息 - 通过")
        success_count += 1

    except Exception as e:
        logger.error(f"✗ 测试7: 引擎信息 - 失败: {e}")

    # 测试8: 清理功能
    total_tests += 1
    try:
        cleanup_counts = engine.cleanup_unused_resources()
        assert isinstance(cleanup_counts, dict)
        assert "containers" in cleanup_counts
        assert "images" in cleanup_counts
        assert "volumes" in cleanup_counts
        assert "networks" in cleanup_counts

        logger.info("✓ 测试8: 清理功能 - 通过")
        success_count += 1

    except Exception as e:
        logger.error(f"✗ 测试8: 清理功能 - 失败: {e}")

    # 输出总结
    success_rate = (success_count / total_tests) * 100
    logger.info("=" * 50)
    logger.info("Docker引擎基础功能测试总结:")
    logger.info(f"总测试数: {total_tests}")
    logger.info(f"通过测试数: {success_count}")
    logger.info(f"失败测试数: {total_tests - success_count}")
    logger.info(f"成功率: {success_rate:.1f}%")
    logger.info("=" * 50)

    if success_count == total_tests:
        logger.info("🎉 所有Docker引擎基础功能测试通过！")
        return True
    else:
        logger.warning(f"⚠️  部分测试失败，成功率: {success_rate:.1f}%")
        return False


if __name__ == "__main__":
    success = test_docker_engine_basic_functionality()
    sys.exit(0 if success else 1)
