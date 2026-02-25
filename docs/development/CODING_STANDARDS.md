# ptest 开发规范文档 / ptest Development Standards

> 版本: 1.0.0  
> 最后更新: 2026-02-09  
> 适用范围: 所有 ptest 项目代码

---

## 目录

1. [字符编码规范](#字符编码规范)
2. [代码风格规范](#代码风格规范)
3. [命名规范](#命名规范)
4. [注释规范](#注释规范)
5. [导入规范](#导入规范)
6. [类型注解规范](#类型注解规范)
7. [错误处理规范](#错误处理规范)
8. [代码质量检查](#代码质量检查)
9. [测试规范](#测试规范)
10. [提交规范](#提交规范)

---

## 字符编码规范

### 强制要求

**所有代码文件必须使用 UTF-8 编码（无 BOM）**

```python
# -*- coding: utf-8 -*-
"""模块文档字符串 / Module docstring

模块描述信息
"""
```

### 文件头模板

每个 Python 文件必须在开头添加编码声明：

```python
# -*- coding: utf-8 -*-
# ptest 模块名称 / ptest Module Name
#
# 版权所有 (c) 2026 cp
# Copyright (c) 2026 ptest Development Team
#
# 许可证: MIT
# License: MIT

"""
模块功能描述 / Module function description

详细描述模块的功能、用途和使用方法。
Detailed description of module functionality, usage and methods.
"""

from __future__ import annotations

# 导入语句...
```

### 跨平台编码注意事项

1. **文件保存**: 确保 IDE/编辑器使用 UTF-8 编码保存文件
2. **换行符**: 使用 LF (`\n`) 换行符，避免 CRLF (`\r\n`)
3. **特殊字符**: 避免使用中文标点符号（、，。）作为代码字符

### 编码检查命令

```bash
# 检查文件编码
file -i src/ptest/*.py

# 转换文件编码（如需要）
iconv -f GBK -t UTF-8 input.py > output.py

# 检查换行符
cat -A src/ptest/module.py | head -5
```

---

## 代码风格规范

### 遵循标准

- **Python**: 遵循 PEP 8 标准
- **代码格式化**: 使用 Ruff 自动格式化
- **行长限制**: 每行不超过 100 个字符

### 缩进和空格

```python
# 正确 ✅
def function_name(param1: str, param2: int) -> bool:
    if param1:
        return True
    return False

# 错误 ❌ - 使用 Tab 缩进
def function_name(param1: str, param2: int) -> bool:
→   if param1:
→   →   return True
→   return False
```

### 空行使用

```python
# 模块级：导入语句后空两行
from __future__ import annotations

import os
import sys

from ptest.core import get_logger


# 类定义前空两行
class MyClass:
    """类文档字符串"""
    
    # 方法之间空一行
    def method1(self):
        pass
    
    def method2(self):
        pass


# 函数定义前空两行
def standalone_function():
    pass
```

---

## 命名规范

### 类名 - PascalCase

```python
# 正确 ✅
class TestFramework:
    pass

class IsolationManager:
    pass

class APIGenerator:
    pass

# 错误 ❌
class test_framework:
class isolationManager:
class API_Generator:
```

### 函数和变量 - snake_case

```python
# 正确 ✅
def create_environment():
    pass

def get_status_info():
    pass

isolation_level = "basic"
environment_manager = None
max_retry_count = 3

# 错误 ❌
def CreateEnvironment():
def getStatusInfo():
    
IsolationLevel = "basic"
environmentManager = None
```

### 常量 - UPPER_CASE

```python
# 正确 ✅
DEFAULT_CONFIG = {}
MAX_ENVIRONMENTS = 100
LOG_LEVEL = "INFO"
TIMEOUT_SECONDS = 300

# 错误 ❌
default_config = {}
maxEnvironments = 100
LogLevel = "INFO"
```

### 私有成员

```python
class MyClass:
    def __init__(self):
        # 单下划线：受保护（模块内部使用）
        self._protected_var = "protected"
        
        # 双下划线：私有（类内部使用，名称修饰）
        self.__private_var = "private"
    
    def _protected_method(self):
        """受保护方法"""
        pass
    
    def __private_method(self):
        """私有方法"""
        pass
```

### 特殊方法

```python
class MyClass:
    # 双下划线开头和结尾：魔术方法
    def __init__(self):
        pass
    
    def __str__(self) -> str:
        return "MyClass instance"
    
    def __repr__(self) -> str:
        return f"MyClass()"
```

---

## 注释规范

### 模块文档字符串

**必须使用中文或中英文双语**

```python
# -*- coding: utf-8 -*-
"""ptest 数据生成模块 / ptest Data Generator Module

提供各种类型的测试数据生成功能，支持单条生成、批量生成、模板生成等。
Provides various types of test data generation capabilities including 
single generation, batch generation, and template generation.

主要功能 / Main Features:
    - 30+ 种数据类型支持
    - Faker 库集成
    - 多种输出格式（JSON/YAML/CSV）
    - 数据模板系统
    - 随机种子支持（确定性生成）

示例 / Example:
    >>> from ptest.data import DataGenerator
    >>> generator = DataGenerator()
    >>> data = generator.generate("name", count=5)
"""
```

### 类文档字符串

```python
class DataGenerator:
    """数据生成器主类 / Data Generator Main Class
    
    提供基于 Faker 的测试数据生成功能。
    Provides test data generation based on Faker.
    
    Attributes:
        config: 数据生成配置 / Data generation configuration
        _faker: Faker 实例（内部使用）
        _rng: 随机数生成器
    
    Example:
        >>> config = DataGenerationConfig(locale="zh_CN", seed=42)
        >>> generator = DataGenerator(config)
        >>> result = generator.generate("email", count=3)
    """
```

### 函数文档字符串

```python
def generate(
    self, 
    data_type: str | DataType, 
    count: int = 1, 
    format: str = "json"
) -> Any:
    """
    生成测试数据 / Generate test data
    
    根据指定的数据类型生成测试数据，支持单条和批量生成。
    Generate test data based on specified type, supports single and batch generation.
    
    Args:
        data_type: 数据类型 / Data type (e.g., "name", "email", "uuid")
        count: 生成数量 / Number of items to generate (default: 1)
        format: 输出格式 / Output format - "json", "yaml", "csv", "raw"
    
    Returns:
        生成的数据 / Generated data:
            - format="json": JSON 字符串
            - format="yaml": YAML 字符串
            - format="csv": CSV 格式字符串
            - format="raw": Python 原生类型
    
    Raises:
        ValueError: 当数据类型不支持时 / When data type is not supported
        ValueError: 当 count <= 0 时
    
    Example:
        >>> generator = DataGenerator()
        >>> # 单条生成
        >>> name = generator.generate("name", count=1, format="raw")
        >>> # 批量生成
        >>> emails = generator.generate("email", count=10, format="json")
    """
```

### 行内注释

**使用中文注释**

```python
# 正确 ✅
# 初始化数据生成器
self._generator = DataGenerator()

# 验证输入参数
if count <= 0:
    raise ValueError("count must be positive")

# 错误 ❌ - 使用英文注释（不符合规范）
# Initialize the data generator
self._generator = DataGenerator()

# 错误 ❌ - 使用中文标点符号
# 初始化数据生成器，验证输入参数。
self._generator = DataGenerator()
```

### 禁止使用中文标点符号

```python
# 错误 ❌ - 使用了中文逗号、顿号、句号
提供测试套件管理功能，支持用例组织、依赖关系和批量执行。

# 正确 ✅ - 使用英文标点或注释
# 提供测试套件管理功能，支持用例组织、依赖关系和批量执行
# Provide test suite management, supporting case organization, 
# dependency relationships and batch execution
```

---

## 导入规范

### 导入顺序

```python
# -*- coding: utf-8 -*-
"""模块文档"""

from __future__ import annotations

# 1. 标准库导入
import json
import os
import sys
from pathlib import Path
from typing import Any

# 2. 第三方库导入
import pytest
import requests
from faker import Faker

# 3. 本地导入 - 绝对导入
from ptest.core import get_logger
from ptest.utils import print_colored

# 4. 本地导入 - 相对导入（同包内）
from .generator import DataGenerator
from .config import DataGenerationConfig
```

### 导入格式

```python
# 正确 ✅ - 每个导入单独一行
import os
import sys
from pathlib import Path

from ptest.core import get_logger
from ptest.utils import print_colored, format_message

# 错误 ❌ - 多个导入在同一行
import os, sys, json
from ptest.core import get_logger, Config, Utils

# 错误 ❌ - 使用通配符导入
from ptest.data import *
```

---

## 类型注解规范

### 基本类型注解

```python
# Python 3.10+ 语法（推荐）
def function(param: str | None) -> int | None:
    pass

# 避免使用旧语法
def function(param: Optional[str]) -> Optional[int]:
    pass
```

### 复杂类型注解

```python
from typing import Any

def process_data(
    data: dict[str, Any],
    items: list[str],
    callback: callable[[str], bool]
) -> tuple[bool, list[str]]:
    """处理数据"""
    pass
```

### 类成员类型注解

```python
class MyClass:
    # 类变量
    DEFAULT_VALUE: int = 100
    
    def __init__(self) -> None:
        # 实例变量
        self.name: str = ""
        self.items: list[str] = []
        self.config: dict[str, Any] | None = None
        self._private_var: int = 0
```

### 返回值类型注解

```python
# 所有函数必须有返回值类型注解
def get_name(self) -> str:
    return self.name

def process(self) -> None:
    """无返回值"""
    pass

def find_item(self, id: str) -> Item | None:
    """可能返回 None"""
    return self._items.get(id)
```

---

## 错误处理规范

### 异常捕获

```python
# 正确 ✅ - 捕获具体异常
try:
    result = risky_operation()
except ValueError as e:
    logger.error(f"Invalid value: {e}")
    raise
except FileNotFoundError as e:
    logger.warning(f"File not found: {e}")
    return None
except Exception as e:
    logger.error(f"Unexpected error: {e}")
    raise

# 错误 ❌ - 捕获所有异常但不处理
try:
    result = risky_operation()
except:
    pass
```

### 资源管理

```python
# 正确 ✅ - 使用上下文管理器
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 正确 ✅ - 使用 try-finally
conn = sqlite3.connect(db_path)
try:
    cursor = conn.cursor()
    cursor.execute(query)
    result = cursor.fetchall()
finally:
    conn.close()

# 错误 ❌ - 资源可能不释放
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute(query)  # 如果这里异常，conn 未关闭
conn.close()
```

### 错误日志记录

```python
# 正确 ✅ - 记录足够的信息
logger.error(f"Failed to load suite '{suite_name}': {e}")
logger.exception("Unexpected error during execution")  # 包含堆栈

# 错误 ❌ - 信息不足
logger.error("Error occurred")
```

---

## 代码质量检查

### 强制检查流程

**每次提交前必须执行：**

```bash
# 1. Ruff 语法和风格检查
uv run ruff check src/ptest/

# 2. Ruff 格式检查
uv run ruff format --check src/ptest/

# 3. Ruff 自动修复（可选）
uv run ruff check --fix src/ptest/

# 4. Ruff 自动格式化（可选）
uv run ruff format src/ptest/

# 5. MyPy 类型检查
uv run mypy src/ptest/

# 6. 运行测试
uv run pytest tests/ -q
```

### 提交前检查清单

- [ ] 文件编码为 UTF-8（无 BOM）
- [ ] 文件头包含编码声明 `# -*- coding: utf-8 -*-`
- [ ] Ruff 检查通过（0 errors）
- [ ] Ruff 格式符合规范
- [ ] MyPy 无关键错误（或通过配置忽略）
- [ ] 所有测试通过
- [ ] 注释使用中文或中英文双语
- [ ] 无中文标点符号作为代码字符

### 处理第三方库类型错误

```python
# 第三方库缺少类型 stubs
import yaml  # type: ignore[import-untyped]

# 或在 pyproject.toml 中配置
[[tool.mypy.overrides]]
module = [
    "ptest.data.*",
]
ignore_errors = true
```

---

## 测试规范

### 测试文件结构

```python
# tests/test_module.py
# -*- coding: utf-8 -*-
"""模块测试 / Module Tests"""

import pytest
from ptest.module import MyClass


class TestMyClass:
    """MyClass 测试"""
    
    def test_initialization(self):
        """测试初始化"""
        obj = MyClass()
        assert obj.name == ""
    
    def test_functionality(self):
        """测试功能"""
        obj = MyClass()
        result = obj.process()
        assert result is True


class TestEdgeCases:
    """边界条件测试"""
    
    def test_empty_input(self):
        """测试空输入"""
        pass
    
    def test_invalid_input(self):
        """测试无效输入"""
        pass
```

### 测试命名规范

- 测试文件: `test_*.py`
- 测试类: `Test*` (PascalCase)
- 测试方法: `test_*` (snake_case)
- 测试方法描述: 使用中文描述测试目的

### 测试覆盖率要求

- 核心模块: >= 80%
- 工具模块: >= 60%
- CLI 模块: >= 50%

---

## 提交规范

### Git 提交信息

```
<type>(<scope>): <subject>

<body>

<footer>
```

**类型 (type):**
- `feat`: 新功能
- `fix`: 修复
- `docs`: 文档
- `style`: 格式（不影响代码运行）
- `refactor`: 重构
- `test`: 测试
- `chore`: 构建过程或辅助工具的变动

**示例:**
```
feat(data): add YAML output format support

- Add _to_yaml method to DataGenerator
- Update CLI to support yaml format option
- Add tests for YAML generation

Fixes #123
```

### 提交前检查

```bash
# 1. 检查修改的文件
git status

# 2. 查看 diff
git diff

# 3. 运行代码质量检查
uv run ruff check src/
uv run ruff format --check src/
uv run mypy src/

# 4. 运行测试
uv run pytest tests/ -q

# 5. 提交
git add <files>
git commit -m "type(scope): description"
```

---

## 附录

### A. 文件模板

#### Python 模块模板

```python
# -*- coding: utf-8 -*-
# ptest <模块名称> / ptest <Module Name>
#
# 版权所有 (c) 2026 cp
# Copyright (c) 2026 ptest Development Team
#
# 许可证: MIT
# License: MIT

"""
<模块功能描述> / <Module function description>

<详细描述>

主要功能 / Main Features:
    - <功能1>
    - <功能2>

示例 / Example:
    >>> from ptest.<module> import <Class>
    >>> obj = <Class>()
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from ptest.core import get_logger

logger = get_logger("<module_name>")


# 常量定义
DEFAULT_VALUE = 100
MAX_COUNT = 1000


class MyClass:
    """
    类描述 / Class description
    """
    
    def __init__(self) -> None:
        """初始化 / Initialize"""
        self.name: str = ""
    
    def method(self) -> None:
        """方法描述 / Method description"""
        pass


if __name__ == "__main__":
    # 模块测试代码
    pass
```

### B. 常见错误及修复

#### 错误1: 中文标点符号

```python
# 错误 ❌
提供测试套件管理功能，支持用例组织、依赖关系和批量执行。

# 修复 ✅
# 提供测试套件管理功能，支持用例组织、依赖关系和批量执行
```

#### 错误2: 类型注解语法

```python
# 错误 ❌
self._suites = dict[str, TestSuite] = {}

# 修复 ✅
self._suites: dict[str, TestSuite] = {}
```

#### 错误3: 资源未释放

```python
# 错误 ❌
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute(query)
conn.close()

# 修复 ✅
conn = sqlite3.connect(db_path)
try:
    cursor = conn.cursor()
    cursor.execute(query)
finally:
    conn.close()

# 或更佳 ✅
with sqlite3.connect(db_path) as conn:
    cursor = conn.cursor()
    cursor.execute(query)
```

### C. 工具和配置

#### VS Code 配置

```json
// .vscode/settings.json
{
    "files.encoding": "utf8",
    "files.insertFinalNewline": true,
    "files.trimTrailingWhitespace": true,
    "python.defaultInterpreterPath": "./.venv/bin/python",
    "editor.formatOnSave": true,
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.rulers": [100],
    "python.analysis.typeCheckingMode": "basic"
}
```

#### PyCharm 配置

1. **编码设置**: File → Settings → Editor → File Encodings → UTF-8
2. **换行符**: Settings → Editor → Code Style → Line separator → LF
3. **行长度**: Settings → Editor → Code Style → Hard wrap at: 100

---

## 参考文档

- [PEP 8 - Python 代码风格指南](https://pep8.org/)
- [Ruff 文档](https://docs.astral.sh/ruff/)
- [MyPy 文档](https://mypy.readthedocs.io/)
- [Python 类型注解最佳实践](https://typing.readthedocs.io/)

---

**维护者**: cp  
**最后更新**: 2026-02-09  
**版本**: 1.0.0
