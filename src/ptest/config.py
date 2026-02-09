# ptest/config.py
import json
import os
import re
from pathlib import Path
from typing import Any

from .core import get_logger

logger = get_logger("config")

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
    """加载配置文件（支持 JSON 和 YAML）"""
    if not config_file.exists():
        return DEFAULT_CONFIG.copy()

    try:
        content = config_file.read_text(encoding="utf-8")

        # 替换环境变量
        content = expand_env_vars(content)

        if config_file.suffix in [".yaml", ".yml"]:
            try:
                import yaml  # type: ignore[import-untyped]

                config = yaml.safe_load(content)
            except ImportError:
                logger.warning("PyYAML not installed, falling back to JSON")
                config = json.loads(content)
        else:
            config = json.loads(content)

        if config and isinstance(config, dict):
            merged = DEFAULT_CONFIG.copy()
            merged.update(config)
            return merged
        return DEFAULT_CONFIG.copy()

    except Exception as e:
        logger.error(f"Failed to load config from {config_file}: {e}")
        return DEFAULT_CONFIG.copy()


def save_config(config: dict, config_file: Path) -> None:
    """保存配置文件"""
    config_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        if config_file.suffix in [".yaml", ".yml"]:
            try:
                import yaml  # type: ignore[import-untyped]

                with open(config_file, "w", encoding="utf-8") as f:
                    yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
            except ImportError:
                logger.warning("PyYAML not installed, saving as JSON")
                with open(config_file, "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=2, ensure_ascii=False)
        else:
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Failed to save config to {config_file}: {e}")


def expand_env_vars(content: str) -> str:
    """
    展开环境变量
    支持格式：
    - $VAR 或 ${VAR}
    - ${VAR:-default} 带默认值
    - ${VAR:+replacement} 如果设置则替换
    """
    pattern = r"\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)"

    def replace(match: re.Match) -> str:
        var_expr = match.group(1) or match.group(2)

        # 处理默认值语法 ${VAR:-default}
        if ":-" in var_expr:
            var_name, default = var_expr.split(":-", 1)
            return os.environ.get(var_name, "") or default

        # 处理替换语法 ${VAR:+replacement}
        if ":+" in var_expr:
            var_name, replacement = var_expr.split(":+", 1)
            return replacement if var_name in os.environ else ""

        return os.environ.get(var_expr, "")

    return re.sub(pattern, replace, content)


def validate_config(config: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    验证配置有效性

    Returns:
        (是否有效, 错误信息列表)
    """
    errors = []

    # 检查必需字段
    required_fields = ["log_level", "report_format"]
    for field in required_fields:
        if field not in config:
            errors.append(f"Missing required field: {field}")

    # 检查 log_level
    valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    if config.get("log_level") not in valid_log_levels:
        errors.append(f"Invalid log_level. Must be one of: {valid_log_levels}")

    # 检查 report_format
    valid_formats = ["html", "json", "markdown"]
    if config.get("report_format") not in valid_formats:
        errors.append(f"Invalid report_format. Must be one of: {valid_formats}")

    # 检查数值范围
    if config.get("max_concurrent_tests", 1) < 1:
        errors.append("max_concurrent_tests must be >= 1")

    if config.get("timeout_seconds", 1) < 1:
        errors.append("timeout_seconds must be >= 1")

    # 检查 isolation 配置
    if "isolation" in config:
        valid_levels = ["basic", "virtualenv", "docker"]
        for level in config["isolation"]:
            if level not in valid_levels:
                errors.append(f"Invalid isolation level: {level}")

    return len(errors) == 0, errors


def generate_config(template: str = "minimal") -> dict[str, Any]:
    """
    生成配置模板

    Args:
        template: 模板类型 (minimal/full/api/database)

    Returns:
        配置字典
    """
    if template == "minimal":
        return {
            "log_level": "INFO",
            "report_format": "html",
            "max_concurrent_tests": 5,
            "timeout_seconds": 300,
        }
    elif template == "api":
        return {
            "log_level": "INFO",
            "report_format": "html",
            "max_concurrent_tests": 10,
            "timeout_seconds": 300,
            "default_isolation_level": "basic",
            "network": {
                "default_port_range": "20000-21000",
                "network_isolation": True,
            },
        }
    elif template == "database":
        return {
            "log_level": "INFO",
            "report_format": "html",
            "max_concurrent_tests": 5,
            "timeout_seconds": 600,
            "default_db_user": "root",
            "default_db_password": "",
            "default_db_host": "localhost",
            "default_db_port": 3306,
        }
    elif template == "full":
        return DEFAULT_CONFIG.copy()
    else:
        return DEFAULT_CONFIG.copy()
