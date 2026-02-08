"""测试数据生成模块的单元测试"""

import json
import pytest
from pathlib import Path

from ptest.data.generator import (
    DataGenerator,
    DataGenerationConfig,
    DataType,
    DataTemplate,
    generate_data,
    quick_generate,
)


class TestDataGenerationConfig:
    """测试数据生成配置"""

    def test_default_config(self):
        """测试默认配置"""
        config = DataGenerationConfig()
        assert config.locale == "zh_CN"
        assert config.seed is None
        assert config.custom_providers == {}

    def test_custom_config(self):
        """测试自定义配置"""
        config = DataGenerationConfig(
            locale="en_US", seed=42, custom_providers={"test": lambda: "value"}
        )
        assert config.locale == "en_US"
        assert config.seed == 42
        assert "test" in config.custom_providers
        assert callable(config.custom_providers["test"])


class TestDataGenerator:
    """测试数据生成器"""

    def test_init(self):
        """测试初始化"""
        generator = DataGenerator()
        assert generator.config is not None

    def test_generate_single_name(self):
        """测试生成单个人名"""
        generator = DataGenerator()
        result = generator.generate("name", count=1, format="raw")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_generate_multiple_emails(self):
        """测试生成多个邮箱"""
        generator = DataGenerator()
        result = generator.generate("email", count=3, format="json")
        data = json.loads(result)
        assert len(data) == 3
        assert all("@" in email for email in data)

    def test_generate_uuid(self):
        """测试生成UUID"""
        generator = DataGenerator()
        result = generator.generate("uuid", count=1, format="raw")
        assert len(result) == 36  # UUID标准长度
        assert result.count("-") == 4

    def test_generate_integer(self):
        """测试生成整数"""
        generator = DataGenerator()
        result = generator.generate("integer", count=1, format="raw")
        assert isinstance(result, int)
        assert 1 <= result <= 1000

    def test_generate_boolean(self):
        """测试生成布尔值"""
        generator = DataGenerator()
        result = generator.generate("boolean", count=1, format="raw")
        assert isinstance(result, bool)

    def test_generate_from_template(self):
        """测试从模板生成数据"""
        generator = DataGenerator()
        template = {
            "name": "{{name}}",
            "email": "{{email}}",
        }
        results = generator.generate_from_template(template, count=2)
        assert len(results) == 2
        for result in results:
            assert "name" in result
            assert "email" in result
            assert "@" in result["email"]

    def test_list_supported_types(self):
        """测试列出支持的数据类型"""
        generator = DataGenerator()
        types = generator.list_supported_types()
        assert len(types) >= 20  # 至少支持20种类型
        assert "name" in types
        assert "email" in types
        assert "uuid" in types

    def test_invalid_data_type(self):
        """测试无效的数据类型"""
        generator = DataGenerator()
        with pytest.raises(ValueError):
            generator.generate("invalid_type", count=1)


class TestDataTemplate:
    """测试数据模板管理器"""

    def test_init(self, tmp_path):
        """测试初始化"""
        manager = DataTemplate(str(tmp_path))
        assert manager.templates_dir == tmp_path

    def test_save_and_load_template(self, tmp_path):
        """测试保存和加载模板"""
        manager = DataTemplate(str(tmp_path))
        template = {"name": "{{name}}", "email": "{{email}}"}

        manager.save_template("test", template)
        loaded = manager.load_template("test")

        assert loaded == template

    def test_load_nonexistent_template(self, tmp_path):
        """测试加载不存在的模板"""
        manager = DataTemplate(str(tmp_path))
        result = manager.load_template("nonexistent")
        assert result is None

    def test_list_templates(self, tmp_path):
        """测试列出模板"""
        manager = DataTemplate(str(tmp_path))
        manager.save_template("template1", {"a": 1})
        manager.save_template("template2", {"b": 2})

        templates = manager.list_templates()
        assert "template1" in templates
        assert "template2" in templates


class TestConvenienceFunctions:
    """测试便捷函数"""

    def test_generate_data(self):
        """测试generate_data函数"""
        result = generate_data("name", count=1, format="raw")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_quick_generate(self):
        """测试quick_generate函数"""
        result = quick_generate("email")
        assert isinstance(result, str)
        assert "@" in result


class TestDataTypes:
    """测试各种数据类型"""

    @pytest.mark.parametrize(
        "data_type",
        [
            "name",
            "email",
            "phone",
            "address",
            "uuid",
            "url",
            "ip",
            "domain",
            "company",
            "job",
            "date",
            "time",
            "datetime",
            "text",
            "integer",
            "float",
            "boolean",
            "username",
            "password",
        ],
    )
    def test_data_types(self, data_type):
        """测试各种数据类型都能正常生成"""
        generator = DataGenerator()
        result = generator.generate(data_type, count=1, format="raw")
        assert result is not None
        assert result != "unknown"
