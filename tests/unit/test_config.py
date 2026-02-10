# -*- coding: utf-8 -*-
"""配置管理模块单元测试 / Config Module Unit Tests"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from ptest.config import Config, ConfigError, ConfigValidator, TemplateManager


class TestConfig:
    """Config类测试"""

    def test_config_creation(self):
        """测试配置创建"""
        config = Config(name="test_config")
        assert config.name == "test_config"
        assert config.config_data == {}

    def test_config_set_get(self):
        """测试配置设置和获取"""
        config = Config(name="test")
        config.set("key1", "value1")
        config.set("nested.key2", "value2")

        assert config.get("key1") == "value1"
        assert config.get("nested.key2") == "value2"

    def test_config_get_with_default(self):
        """测试获取带默认值"""
        config = Config(name="test")
        assert config.get("nonexistent", "default") == "default"

    def test_config_from_dict(self):
        """测试从字典创建"""
        data = {"name": "test", "value": 123, "nested": {"key": "value"}}
        config = Config.from_dict(data)

        assert config.name == "test"
        assert config.get("value") == 123
        assert config.get("nested.key") == "value"

    def test_config_to_dict(self):
        """测试转换为字典"""
        config = Config(name="test")
        config.set("key", "value")

        data = config.to_dict()
        assert data["name"] == "test"
        assert data["key"] == "value"

    def test_config_save_and_load(self):
        """测试保存和加载"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"

            config = Config(name="test")
            config.set("key", "value")
            config.save(config_file)

            loaded = Config.load(config_file)
            assert loaded.name == "test"
            assert loaded.get("key") == "value"

    def test_config_load_nonexistent(self):
        """测试加载不存在的文件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ConfigError):
                Config.load(Path(tmpdir) / "nonexistent.yaml")


class TestConfigValidator:
    """ConfigValidator测试"""

    def test_validate_valid_config(self):
        """测试验证有效配置"""
        config = Config(name="test")
        config.set("log_level", "INFO")
        config.set("timeout", 30)

        validator = ConfigValidator()
        is_valid, errors = validator.validate(config)

        assert is_valid is True
        assert errors == []

    def test_validate_invalid_log_level(self):
        """测试验证无效的日志级别"""
        config = Config(name="test")
        config.set("log_level", "INVALID")

        validator = ConfigValidator()
        is_valid, errors = validator.validate(config)

        assert is_valid is False
        assert any("log_level" in error.lower() for error in errors)

    def test_validate_negative_timeout(self):
        """测试验证负超时"""
        config = Config(name="test")
        config.set("timeout", -1)

        validator = ConfigValidator()
        is_valid, errors = validator.validate(config)

        assert is_valid is False
        assert any("timeout" in error.lower() for error in errors)


class TestTemplateManager:
    """TemplateManager测试"""

    def test_get_minimal_template(self):
        """测试获取最小模板"""
        manager = TemplateManager()
        template = manager.get_template("minimal")

        assert template is not None
        assert "name" in template

    def test_get_full_template(self):
        """测试获取完整模板"""
        manager = TemplateManager()
        template = manager.get_template("full")

        assert template is not None
        assert len(template) > 0

    def test_get_api_template(self):
        """测试获取API模板"""
        manager = TemplateManager()
        template = manager.get_template("api")

        assert template is not None

    def test_get_database_template(self):
        """测试获取数据库模板"""
        manager = TemplateManager()
        template = manager.get_template("database")

        assert template is not None

    def test_get_invalid_template(self):
        """测试获取无效模板"""
        manager = TemplateManager()
        template = manager.get_template("invalid")

        assert template is None

    def test_list_templates(self):
        """测试列出所有模板"""
        manager = TemplateManager()
        templates = manager.list_templates()

        assert "minimal" in templates
        assert "full" in templates
        assert "api" in templates
        assert "database" in templates


class TestEnvironmentVariableExpansion:
    """环境变量展开测试"""

    def test_expand_simple_variable(self):
        """测试展开简单变量"""
        os.environ["TEST_VAR"] = "test_value"

        config = Config(name="test")
        config.set("key", "$TEST_VAR")

        expanded = config.expand_env_vars(config.get("key"))
        assert expanded == "test_value"

    def test_expand_braced_variable(self):
        """测试展开大括号变量"""
        os.environ["TEST_VAR2"] = "test_value2"

        config = Config(name="test")
        config.set("key", "${TEST_VAR2}")

        expanded = config.expand_env_vars(config.get("key"))
        assert expanded == "test_value2"

    def test_expand_with_default(self):
        """测试展开带默认值"""
        config = Config(name="test")
        config.set("key", "${NONEXISTENT:-default}")

        expanded = config.expand_env_vars(config.get("key"))
        assert expanded == "default"

    def test_no_expansion_for_regular_string(self):
        """测试普通字符串不展开"""
        config = Config(name="test")
        config.set("key", "regular_string")

        expanded = config.expand_env_vars(config.get("key"))
        assert expanded == "regular_string"
