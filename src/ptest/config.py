# ptest/config.py
import json
from pathlib import Path
from typing import Any

DEFAULT_CONFIG = {
    "log_level": "INFO",
    "report_format": "html",
    "max_concurrent_tests": 5,
    "timeout_seconds": 300,
    "default_db_user": "root",
    "default_db_password": "",
    "default_db_host": "localhost",
    "default_db_port": 3306,
    # 隔离配置
    "default_isolation_level": "basic",
    "max_environments": 100,
    "cleanup_policy": "on_request",
    "isolation": {
        "basic": {
            "enabled": True,
            "description": "基础目录隔离",
            "capabilities": ["filesystem", "basic_process"],
        },
        "virtualenv": {
            "enabled": True,
            "description": "Python虚拟环境隔离",
            "capabilities": ["filesystem", "process", "package_isolation"],
            "python_executable": None,
            "clear_cache": True,
            "system_site_packages": False,
            "base_packages": ["setuptools", "wheel", "pip"],
            "resource_limits": {
                "max_processes": 100,
                "memory_mb": 1024,
                "disk_space_mb": 2048,
            },
        },
        "docker": {
            "enabled": True,
            "description": "Docker容器隔离",
            "capabilities": [
                "filesystem",
                "process",
                "network",
                "package_isolation",
                "resource_limits",
            ],
            "default_image": "python:3.9-slim",
            "network_name": "ptest_isolation",
            "default_resource_limits": {
                "memory_limit": "512m",
                "cpu_limit": 1.0,
                "disk_space_gb": 5,
            },
            "security": {
                "user": "nobody",
                "capabilities_drop": ["ALL"],
                "read_only": ["/usr", "/lib", "/bin"],
                "tmpfs": ["/tmp", "/var/tmp"],
            },
        },
    },
    "network": {
        "default_port_range": "20000-21000",
        "port_allocation_timeout": 30,
        "network_isolation": True,
        "firewall_rules_enabled": False,
    },
    "resource_monitoring": {
        "enabled": True,
        "update_interval": 5,
        "alert_thresholds": {
            "cpu_percent": 80.0,
            "memory_mb": 2048,
            "disk_space_mb": 10240,
        },
    },
}


def load_config(config_file: Path) -> dict[str, Any]:
    """加载配置文件"""
    if config_file.exists():
        with open(config_file, "r") as f:
            config = json.load(f)
        DEFAULT_CONFIG.update(config)
    return DEFAULT_CONFIG


def save_config(config: dict, config_file: Path) -> None:
    """保存配置文件"""
    with open(config_file, "w") as f:
        json.dump(config, f, indent=2)
