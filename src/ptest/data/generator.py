"""ptest 数据生成模块 - 基于Faker的测试数据生成器

提供各种类型的测试数据生成功能，支持单条生成、批量生成、模板生成等。
"""

from __future__ import annotations

import json
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any


class DataType(str, Enum):
    """支持的数据类型枚举"""

    # 基础数据
    NAME = "name"
    CHINESE_NAME = "chinese_name"
    ENGLISH_NAME = "english_name"
    PHONE = "phone"
    EMAIL = "email"
    ADDRESS = "address"
    ID_CARD = "id_card"
    UUID = "uuid"

    # 网络数据
    URL = "url"
    IP = "ip"
    IPV4 = "ipv4"
    IPV6 = "ipv6"
    DOMAIN = "domain"
    MAC_ADDRESS = "mac_address"

    # 业务数据
    COMPANY = "company"
    JOB = "job"
    USERNAME = "username"
    PASSWORD = "password"
    CREDIT_CARD = "credit_card"

    # 时间数据
    DATE = "date"
    TIME = "time"
    DATETIME = "datetime"
    TIMESTAMP = "timestamp"

    # 文本数据
    TEXT = "text"
    SENTENCE = "sentence"
    PARAGRAPH = "paragraph"
    WORD = "word"

    # 数值数据
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"


@dataclass
class DataGenerationConfig:
    """数据生成配置"""

    locale: str = "zh_CN"  # 默认中文
    seed: int | None = None  # 随机种子，用于可重复生成
    custom_providers: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.seed is not None:
            random.seed(self.seed)


class DataGenerator:
    """数据生成器主类"""

    def __init__(self, config: DataGenerationConfig | None = None):
        self.config = config or DataGenerationConfig()
        self._faker = None
        self._init_faker()

    def _init_faker(self):
        """初始化Faker实例"""
        try:
            from faker import Faker

            self._faker = Faker(self.config.locale)
            if self.config.seed is not None:
                self._faker.seed_instance(self.config.seed)
        except ImportError:
            self._faker = None

    def generate(
        self, data_type: str | DataType, count: int = 1, format: str = "json"
    ) -> list[dict[str, Any]] | list[str] | str:
        """
        生成测试数据

        Args:
            data_type: 数据类型
            count: 生成数量
            format: 输出格式 (json, yaml, csv, raw)

        Returns:
            生成的数据
        """
        data_type = DataType(data_type) if isinstance(data_type, str) else data_type

        results = []
        for _ in range(count):
            value = self._generate_single(data_type)
            results.append(value)

        if format == "raw":
            return results[0] if count == 1 else results
        elif format == "json":
            return json.dumps(results, ensure_ascii=False, indent=2)
        elif format == "yaml":
            return self._to_yaml(results)
        elif format == "csv":
            return self._to_csv(results)
        else:
            raise ValueError(
                f"Unsupported format: {format!r}. Expected one of: 'raw', 'json', 'yaml', 'csv'."
            )

    def _generate_single(self, data_type: DataType) -> Any:
        """生成单条数据"""
        if self._faker:
            return self._generate_with_faker(data_type)
        else:
            return self._generate_fallback(data_type)

    def _generate_with_faker(self, data_type: DataType) -> Any:
        """使用Faker生成数据"""
        assert self._faker is not None, "Faker instance should be initialized"
        faker = self._faker

        generators = {
            # 基础数据
            DataType.NAME: lambda: faker.name(),
            DataType.CHINESE_NAME: lambda: faker.name(),
            DataType.ENGLISH_NAME: lambda: faker.name(),
            DataType.PHONE: lambda: faker.phone_number(),
            DataType.EMAIL: lambda: faker.email(),
            DataType.ADDRESS: lambda: faker.address(),
            DataType.ID_CARD: lambda: (
                faker.ssn()
                if hasattr(faker, "ssn")
                else self._generate_fallback(DataType.ID_CARD)
            ),
            DataType.UUID: lambda: str(uuid.uuid4()),
            # 网络数据
            DataType.URL: lambda: faker.url(),
            DataType.IP: lambda: faker.ipv4(),
            DataType.IPV4: lambda: faker.ipv4(),
            DataType.IPV6: lambda: faker.ipv6(),
            DataType.DOMAIN: lambda: faker.domain_name(),
            DataType.MAC_ADDRESS: lambda: faker.mac_address(),
            # 业务数据
            DataType.COMPANY: lambda: faker.company(),
            DataType.JOB: lambda: faker.job(),
            DataType.USERNAME: lambda: faker.user_name(),
            DataType.PASSWORD: lambda: faker.password(),
            DataType.CREDIT_CARD: lambda: faker.credit_card_number(),
            # 时间数据
            DataType.DATE: lambda: faker.date(),
            DataType.TIME: lambda: faker.time(),
            DataType.DATETIME: lambda: faker.iso8601(),
            DataType.TIMESTAMP: lambda: int(datetime.now().timestamp()),
            # 文本数据
            DataType.TEXT: lambda: faker.text(),
            DataType.SENTENCE: lambda: faker.sentence(),
            DataType.PARAGRAPH: lambda: faker.paragraph(),
            DataType.WORD: lambda: faker.word(),
            # 数值数据
            DataType.INTEGER: lambda: random.randint(1, 1000),
            DataType.FLOAT: lambda: round(random.uniform(1.0, 1000.0), 2),
            DataType.BOOLEAN: lambda: random.choice([True, False]),
        }

        generator = generators.get(data_type)
        if generator:
            try:
                return generator()
            except Exception:
                return self._generate_fallback(data_type)

        return self._generate_fallback(data_type)

    def _generate_fallback(self, data_type: DataType) -> Any:
        """Faker不可用时的备用生成逻辑"""
        fallbacks = {
            DataType.NAME: lambda: random.choice(
                ["张三", "李四", "王五", "赵六", "钱七"]
            ),
            DataType.CHINESE_NAME: lambda: random.choice(
                ["张三", "李四", "王五", "赵六", "钱七"]
            ),
            DataType.ENGLISH_NAME: lambda: random.choice(
                ["John", "Jane", "Bob", "Alice", "Tom"]
            ),
            DataType.PHONE: lambda: (
                f"1{random.choice([3, 4, 5, 7, 8, 9])}{random.randint(100000000, 999999999)}"
            ),
            DataType.EMAIL: lambda: f"user{random.randint(1, 10000)}@example.com",
            DataType.ADDRESS: lambda: f"北京市朝阳区{random.randint(1, 100)}号",
            DataType.ID_CARD: lambda: (
                f"{random.randint(100000, 999999)}{random.randint(10000000, 99999999)}{random.randint(1000, 9999)}"
            ),
            DataType.UUID: lambda: str(uuid.uuid4()),
            DataType.URL: lambda: f"https://example{random.randint(1, 100)}.com",
            DataType.IP: lambda: (
                f"{random.randint(1, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}"
            ),
            DataType.IPV4: lambda: (
                f"{random.randint(1, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}"
            ),
            DataType.IPV6: lambda: "2001:0db8:85a3:0000:0000:8a2e:0370:7334",
            DataType.DOMAIN: lambda: f"example{random.randint(1, 100)}.com",
            DataType.MAC_ADDRESS: lambda: "00:1B:44:11:3A:B7",
            DataType.COMPANY: lambda: random.choice(
                ["科技有限公司", "网络公司", "软件公司"]
            ),
            DataType.JOB: lambda: random.choice(["工程师", "经理", "总监", "专员"]),
            DataType.USERNAME: lambda: f"user{random.randint(1, 10000)}",
            DataType.PASSWORD: lambda: f"Pass{random.randint(1000, 9999)}!",
            DataType.CREDIT_CARD: lambda: (
                f"{random.randint(1000, 9999)}-{random.randint(1000, 9999)}-{random.randint(1000, 9999)}-{random.randint(1000, 9999)}"
            ),
            DataType.DATE: lambda: (
                datetime.now() - timedelta(days=random.randint(0, 365))
            ).strftime("%Y-%m-%d"),
            DataType.TIME: lambda: (
                f"{random.randint(0, 23):02d}:{random.randint(0, 59):02d}:{random.randint(0, 59):02d}"
            ),
            DataType.DATETIME: lambda: datetime.now().isoformat(),
            DataType.TIMESTAMP: lambda: int(datetime.now().timestamp()),
            DataType.TEXT: lambda: "这是一段示例文本内容。",
            DataType.SENTENCE: lambda: "这是一个示例句子。",
            DataType.PARAGRAPH: lambda: "这是一个示例段落。包含多句话的内容。",
            DataType.WORD: lambda: random.choice(["测试", "数据", "示例", "内容"]),
            DataType.INTEGER: lambda: random.randint(1, 1000),
            DataType.FLOAT: lambda: round(random.uniform(1.0, 1000.0), 2),
            DataType.BOOLEAN: lambda: random.choice([True, False]),
        }

        return fallbacks.get(data_type, lambda: "unknown")()

    def _to_yaml(self, data: list[Any]) -> str:
        """转换为YAML格式"""
        try:
            import yaml  # type: ignore[import-untyped]

            return yaml.dump(data, allow_unicode=True, sort_keys=False)
        except ImportError:
            # 简单YAML格式实现
            lines = []
            for i, item in enumerate(data):
                lines.append(f"- {item}")
            return "\n".join(lines)

    def _to_csv(self, data: list[Any]) -> str:
        """转换为CSV格式"""
        if not data:
            return ""

        if isinstance(data[0], dict):
            import csv
            import io

            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
            return output.getvalue()
        else:
            return "\n".join(str(item) for item in data)

    def generate_from_template(
        self, template: dict[str, Any], count: int = 1
    ) -> list[dict[str, Any]]:
        """
        基于模板生成数据

        Args:
            template: 数据模板，支持 {{data_type}} 语法
            count: 生成数量

        Returns:
            生成的数据列表
        """
        results = []
        for _ in range(count):
            result = self._process_template(template)
            results.append(result)
        return results

    def _process_template(self, template: Any) -> Any:
        """处理模板中的变量"""
        if isinstance(template, dict):
            return {k: self._process_template(v) for k, v in template.items()}
        elif isinstance(template, list):
            return [self._process_template(item) for item in template]
        elif isinstance(template, str):
            return self._replace_variables(template)
        else:
            return template

    def _replace_variables(self, text: str) -> str:
        """替换模板变量 {{data_type}}"""
        import re

        pattern = r"\{\{(\w+)\}\}"

        def replace_match(match):
            var_name = match.group(1)
            try:
                data_type = DataType(var_name)
                return str(self._generate_single(data_type))
            except ValueError:
                return match.group(0)

        return re.sub(pattern, replace_match, text)

    def list_supported_types(self) -> list[str]:
        """列出所有支持的数据类型"""
        return [t.value for t in DataType]


class DataTemplate:
    """数据模板管理器"""

    def __init__(self, templates_dir: str | Path | None = None):
        self.templates_dir = (
            Path(templates_dir)
            if templates_dir
            else Path.home() / ".ptest" / "templates"
        )
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        self._templates: dict[str, dict[str, Any]] = {}

    def load_template(self, name: str) -> dict[str, Any] | None:
        """加载模板"""
        template_file = self.templates_dir / f"{name}.json"
        if template_file.exists():
            with open(template_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def save_template(self, name: str, template: dict[str, Any]) -> None:
        """保存模板"""
        template_file = self.templates_dir / f"{name}.json"
        with open(template_file, "w", encoding="utf-8") as f:
            json.dump(template, f, ensure_ascii=False, indent=2)

    def list_templates(self) -> list[str]:
        """列出所有模板"""
        templates = []
        for f in self.templates_dir.glob("*.json"):
            templates.append(f.stem)
        return templates


# 便捷函数
def generate_data(
    data_type: str, count: int = 1, locale: str = "zh_CN", format: str = "json"
) -> Any:
    """
    便捷的数据生成函数

    Args:
        data_type: 数据类型
        count: 生成数量
        locale: 语言区域
        format: 输出格式

    Returns:
        生成的数据
    """
    config = DataGenerationConfig(locale=locale)
    generator = DataGenerator(config)
    return generator.generate(data_type, count=count, format=format)


def quick_generate(data_type: str) -> str:
    """快速生成单条数据"""
    return generate_data(data_type, count=1, format="raw")
