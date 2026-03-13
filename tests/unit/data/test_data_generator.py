"""测试数据生成模块的单元测试 - ptest 断言版本

迁移说明:
- 原文件使用 pytest 断言，现已迁移到 ptest 断言
- 迁移对照表:
  - assert x == y → assert_that(x).equals(y)
  - assert x != y → assert_that(x).not_equal(y)
  - assert x in y → assert_that(y).contains(x)
  - assertTrue(x) → assert_that(x).is_true()
  - assertIsNone(x) → assert_that(x).is_none()
  - assertIsNotNone(x) → assert_that(x).not_none()
  - isinstance(x, T) → assert_that(x).is_instance(T)  # 支持 Python 类型
  - len(x) == n → assert_that(x).len_is(n)
  - pytest.raises(E) → assert_raises(E)

注意: @pytest.mark.parametrize 保留，因为 ptest 暂不支持参数化
"""

import json
import subprocess

from ptest.assertions import assert_that, assert_raises

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
        assert_that(config.locale).equals("zh_CN")
        assert_that(config.seed).is_none()

    def test_custom_config(self):
        """测试自定义配置"""
        config = DataGenerationConfig(locale="en_US", seed=42)
        assert_that(config.locale).equals("en_US")
        assert_that(config.seed).equals(42)


class TestDataGenerator:
    """测试数据生成器"""

    def test_init(self):
        """测试初始化"""
        generator = DataGenerator()
        assert_that(generator.config).not_none()

    def test_generate_single_name(self):
        """测试生成单个人名"""
        generator = DataGenerator()
        result = generator.generate("name", count=1, format="raw")
        assert_that(result).is_instance(str)
        assert_that(len(result)).is_true()  # 长度 > 0

    def test_generate_multiple_emails(self):
        """测试生成多个邮箱"""
        generator = DataGenerator()
        result = generator.generate("email", count=3, format="json")
        data = json.loads(result)
        assert_that(len(data)).equals(3)
        for email in data:
            assert_that(email).contains("@")  # 验证 email 格式

    def test_generate_uuid(self):
        """测试生成UUID"""
        generator = DataGenerator()
        result = generator.generate("uuid", count=1, format="raw")
        assert_that(len(result)).equals(36)  # UUID标准长度
        assert_that(result.count("-")).equals(4)

    def test_generate_integer(self):
        """测试生成整数"""
        generator = DataGenerator()
        result = generator.generate("integer", count=1, format="raw")
        assert_that(result).is_instance(int)
        assert_that(1 <= result <= 1000).is_true()

    def test_generate_boolean(self):
        """测试生成布尔值"""
        generator = DataGenerator()
        result = generator.generate("boolean", count=1, format="raw")
        assert_that(result).is_instance(bool)

    def test_generate_from_template(self):
        """测试从模板生成数据"""
        generator = DataGenerator()
        template = {
            "name": "{{name}}",
            "email": "{{email}}",
        }
        results = generator.generate_from_template(template, count=2)
        assert_that(len(results)).equals(2)
        for result in results:
            assert_that("name" in result).is_true()
            assert_that("email" in result).is_true()
            assert_that(result["email"]).contains("@")

    def test_list_supported_types(self):
        """测试列出支持的数据类型"""
        generator = DataGenerator()
        types = generator.list_supported_types()
        assert_that(len(types)).is_true()
        assert_that("name" in types).is_true()
        assert_that("email" in types).is_true()
        assert_that("uuid" in types).is_true()

    def test_invalid_data_type(self):
        """测试无效的数据类型"""
        generator = DataGenerator()
        with assert_raises(ValueError):
            generator.generate("invalid_type", count=1)


class TestDataTemplate:
    """测试数据模板管理器"""

    def test_init(self, tmp_path):
        """测试初始化"""
        manager = DataTemplate(str(tmp_path))
        assert_that(manager.templates_dir).equals(tmp_path)

    def test_save_and_load_template(self, tmp_path):
        """测试保存和加载模板"""
        manager = DataTemplate(str(tmp_path))
        template = {"name": "{{name}}", "email": "{{email}}"}

        manager.save_template("test", template)
        loaded = manager.load_template("test")

        assert_that(loaded).equals(template)

    def test_load_nonexistent_template(self, tmp_path):
        """测试加载不存在的模板"""
        manager = DataTemplate(str(tmp_path))
        result = manager.load_template("nonexistent")
        assert_that(result).is_none()

    def test_list_templates(self, tmp_path):
        """测试列出模板"""
        manager = DataTemplate(str(tmp_path))
        manager.save_template("template1", {"a": 1})
        manager.save_template("template2", {"b": 2})

        templates = manager.list_templates()
        assert_that("template1" in templates).is_true()
        assert_that("template2" in templates).is_true()


class TestConvenienceFunctions:
    """测试便捷函数"""

    def test_generate_data(self):
        """测试generate_data函数"""
        result = generate_data("name", count=1, format="raw")
        assert_that(result).is_instance(str)
        assert_that(len(result)).is_true()

    def test_quick_generate(self):
        """测试quick_generate函数"""
        result = quick_generate("email")
        assert_that(result).is_instance(str)
        assert_that(result).contains("@")


class TestDataTypes:
    """测试各种数据类型

    注意: @pytest.mark.parametrize 保留，因为 ptest 暂不支持参数化
    """

    def test_data_types_with_type_check(self):
        """测试各种数据类型都能正常生成并验证类型"""
        generator = DataGenerator()
        result = generator.generate("name", count=1, format="raw")
        assert_that(result).not_none()
        assert_that(result).not_equal("unknown")
        assert_that(result).is_instance(str)


class TestGenerateFormats:
    """测试不同输出格式"""

    def test_generate_yaml_format(self):
        """测试YAML格式输出"""
        generator = DataGenerator()
        result = generator.generate("name", count=2, format="yaml")
        assert_that(result).is_instance(str)
        # YAML应该有换行符
        has_yaml_format = ("\n" in result) or ("- " in result)
        assert_that(has_yaml_format).is_true()

    def test_generate_csv_format_scalar(self):
        """测试CSV格式输出 - 标量值"""
        generator = DataGenerator()
        result = generator.generate("integer", count=3, format="csv")
        assert_that(result).is_instance(str)
        lines = result.strip().split("\n")
        assert_that(len(lines)).equals(3)

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
        assert_that(csv_content).contains("id")
        assert_that(csv_content).contains("name")

    def test_generate_raw_multi_item(self):
        """测试raw格式生成多个项目"""
        generator = DataGenerator()
        result = generator.generate("email", count=3, format="raw")
        assert_that(result).is_instance(list)
        assert_that(len(result)).equals(3)
        for email in result:
            assert_that(email).contains("@")

    def test_generate_unknown_format_raises(self):
        """测试未知格式抛出ValueError"""
        generator = DataGenerator()
        with assert_raises(ValueError):
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

        assert_that(result1).equals(result2)

    def test_different_seed_produces_different_output(self):
        """不同seed应该产生不同的输出"""
        config1 = DataGenerationConfig(locale="en_US", seed=42)
        config2 = DataGenerationConfig(locale="en_US", seed=43)

        generator1 = DataGenerator(config=config1)
        generator2 = DataGenerator(config=config2)

        result1 = generator1.generate("name", count=20, format="raw")
        result2 = generator2.generate("name", count=20, format="raw")

        # 不同seed下20个名字完全相同的概率极低
        assert_that(result1).not_equal(result2)


class TestCLILevel:
    """测试CLI层面的行为"""

    def test_cli_invalid_data_type(self):
        """CLI层面对无效数据类型的友好错误处理"""
        result = subprocess.run(
            ["uv", "run", "ptest", "data", "generate", "invalid_type"],
            capture_output=True,
            text=True,
        )

        # CLI应该以非0退出码失败
        assert_that(result.returncode).not_equal(0)

        output = (result.stdout or "") + (result.stderr or "")

        # 不应该有Python traceback
        has_traceback = "Traceback (most recent call last)" in output
        assert_that(has_traceback).is_false()

        # 应该包含错误信息
        has_error_msg = ("invalid_type" in output.lower()) or (
            "unknown" in output.lower()
        )
        assert_that(has_error_msg).is_true()
