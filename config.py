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
    "default_db_port": 3306
}

def load_config(
        config_file:Path
    )-> dict[str, Any]:
    """加载配置文件"""
    if config_file.exists():
        with open(config_file, 'r') as f:
            config = json.load(f)
        DEFAULT_CONFIG.update(config)
    return DEFAULT_CONFIG

def save_config(
        config      :dict, 
        config_file :Path
    ) -> None:
    """保存配置文件"""
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=2)