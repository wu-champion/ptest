# 代码质量检查规范

> 本文档定义新代码文件的代码质量检查流程

## 检查工具

- **Ruff**: 语法检查、格式检查、导入排序
- **MyPy**: 类型检查

## 检查流程

### 1. Ruff 检查

```bash
# 语法和风格检查
uv run ruff check <文件路径>

# 格式检查
uv run ruff format --check <文件路径>

# 自动修复问题
uv run ruff check --fix <文件路径>

# 自动格式化
uv run ruff format <文件路径>
```

### 2. MyPy 检查

```bash
# 类型检查
uv run mypy <文件路径>
```

## 问题处理规则

### 必须修复的问题

1. **Ruff F类错误** (如 F401, F841): 未使用导入、变量
2. **Ruff E类错误** (如 E712, E722): 语法错误
3. **明显的类型错误**: 可以通过代码调整解决的

### 可以忽略的问题

1. **第三方库缺少类型 stubs**: 添加 `# type: ignore[import-untyped]`
   ```python
   import yaml  # type: ignore[import-untyped]
   ```

2. **复杂类型推断**: 在 `pyproject.toml` 中添加模块到忽略列表
   ```toml
   [[tool.mypy.overrides]]
   module = [
       "ptest.data.*",
   ]
   ignore_errors = true
   ```

3. **运行时检查已确保类型安全**: 使用 `assert` 语句
   ```python
   assert self._faker is not None, "Faker should be initialized"
   result = self._faker.name()
   ```

## 代码提交前检查清单

- [ ] Ruff 检查通过 (0 errors)
- [ ] Ruff 格式符合规范
- [ ] MyPy 无关键错误 (或通过配置忽略)
- [ ] 所有测试通过

## 示例

### 修复前
```python
# tests/test_example.py
import json
import pytest
from pathlib import Path  # F401: unused import

from ptest.data import DataType  # F401: unused import
```

### 修复后
```python
# tests/test_example.py
import json
import pytest

from ptest.data import DataGenerator
```

### MyPy 修复示例

```python
# 修复前 - MyPy报错
class MyClass:
    def __init__(self):
        self._optional: SomeType | None = None
    
    def use_it(self):
        return self._optional.method()  # Error: Item "None" has no attribute "method"

# 修复后 - 添加断言
class MyClass:
    def __init__(self):
        self._optional: SomeType | None = None
    
    def use_it(self):
        assert self._optional is not None, "Should be initialized"
        return self._optional.method()
```

## 自动化建议

可以在 CI/CD 中添加以下检查：

```yaml
# .github/workflows/code-quality.yml
- name: Ruff Check
  run: uv run ruff check src/ tests/

- name: Ruff Format Check
  run: uv run ruff format --check src/ tests/

- name: MyPy Check
  run: uv run mypy src/
```
