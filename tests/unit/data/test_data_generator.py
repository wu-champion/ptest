"""测试数据生成模块的单元测试"""

import json
import pytest

from ptest.data.generator import (
    DataGenerator,
    DataGenerationConfig,
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

    def test_custom_config(self):
        """测试自定义配置"""
        config = DataGenerationConfig(locale="en_US", seed=42)
        assert config.locale == "en_US"
        assert config.seed == 42


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
        "data_type,expected_type",
        [
            ("name", str),
            ("email", str),
            ("phone", str),
            ("uuid", str),
            ("integer", int),
            ("float", float),
            ("boolean", bool),
        ],
    )
    def test_data_types_with_type_check(self, data_type, expected_type):
        """测试各种数据类型都能正常生成并验证类型"""
        generator = DataGenerator()
        result = generator.generate(data_type, count=1, format="raw")
        assert result is not None
        assert result != "unknown"
        assert isinstance(result, expected_type)


class TestGenerateFormats:
    """测试不同输出格式"""

    def test_generate_yaml_format(self):
        """测试YAML格式输出"""
        generator = DataGenerator()
        result = generator.generate("name", count=2, format="yaml")
        assert isinstance(result, str)
        # YAML应该有换行符
        assert "\n" in result or "- " in result

    def test_generate_csv_format_scalar(self):
        """测试CSV格式输出 - 标量值"""
        generator = DataGenerator()
        result = generator.generate("integer", count=3, format="csv")
        assert isinstance(result, str)
        lines = result.strip().split("\n")
        assert len(lines) == 3

    def test_generate_csv_format_dict(self):
        """测试CSV格式输出 - 字典值"""
        # 通过模板生成字典数据
        generator = DataGenerator()
        template = {"id": "{{integer}}", "name": "{{name}}"}
        results = generator.generate_from_template(template, count=2)
        # CSV格式需要列表中包含字典
        import csv
        import io

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)
        csv_content = output.getvalue()
        assert "id" in csv_content
        assert "name" in csv_content

    def test_generate_raw_multi_item(self):
        """测试raw格式生成多个项目"""
        generator = DataGenerator()
        result = generator.generate("email", count=3, format="raw")
        assert isinstance(result, list)
        assert len(result) == 3
        assert all("@" in email for email in result)

    def test_generate_unknown_format_raises(self):
        """测试未知格式抛出ValueError"""
        generator = DataGenerator()
        with pytest.raises(ValueError, match="Unsupported format"):
            generator.generate("name", count=1, format="unknown")


class TestSeedDeterminism:
    """测试随机种子确定性"""

    def test_same_seed_produces_same_output(self):
        """相同seed应该产生相同的输出"""
        config1 = DataGenerationConfig(locale="en_US", seed=42)
        config2 = DataGenerationConfig(locale="en_US", seed=42)

        generator1 = DataGenerator(config=config1)
        generator2 = DataGenerator(config=config2)

        result1 = generator1.generate("name", count=5, format="raw")
        result2 = generator2.generate("name", count=5, format="raw")

        assert result1 == result2

    def test_different_seed_produces_different_output(self):
        """不同seed应该产生不同的输出"""
        config1 = DataGenerationConfig(locale="en_US", seed=42)
        config2 = DataGenerationConfig(locale="en_US", seed=43)

        generator1 = DataGenerator(config=config1)
        generator2 = DataGenerator(config=config2)

        result1 = generator1.generate("name", count=20, format="raw")
        result2 = generator2.generate("name", count=20, format="raw")

        # 不同seed下20个名字完全相同的概率极低
        assert result1 != result2


class TestCLILevel:
    """测试CLI层面的行为"""

    def test_cli_invalid_data_type(self):
        """CLI层面对无效数据类型的友好错误处理"""
        import subprocess

        result = subprocess.run(
            ["uv", "run", "ptest", "data", "generate", "invalid_type"],
            capture_output=True,
            text=True,
        )

        # CLI应该以非0退出码失败
        assert result.returncode != 0

        output = (result.stdout or "") + (result.stderr or "")

        # 不应该有Python traceback
        assert "Traceback (most recent call last)" not in output

        # 应该包含错误信息
        assert "invalid_type" in output.lower() or "unknown" in output.lower()
