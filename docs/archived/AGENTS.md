# AGENTS.md

此文件包含在 ptest 仓库中工作的智能编码代理的指南和命令。

## 构建/检查/测试命令

### 安装和设置
```bash
# 以开发模式安装
pip install -e .

# 使用 uv 安装（如果可用）
uv pip install -e .

# 备选安装方式
python setup.py install
```

### 运行框架
```bash
# 主要 CLI 命令
ptest --help                    # 显示帮助
p --help                       # ptest 的简写别名

# 环境管理
ptest init --path ./test_env   # 初始化测试环境
p init --path ./test_env       # 使用简写别名

# 对象管理
ptest obj install mysql my_db --version 9.9.9
ptest obj start my_db
ptest obj stop my_db
ptest obj list
p obj status                    # 显示对象状态

# 测试用例管理
ptest case add test1 '{"type": "api", "endpoint": "/test"}'
ptest case run test1            # 运行单个测试用例
ptest case run all              # 运行所有测试用例
p run all                       # 简写别名

# 报告
ptest report --format html     # 生成 HTML 报告
ptest report --format json     # 生成 JSON 报告

# 状态
ptest status                    # 显示框架状态
p status                       # 简写别名
```

### 运行单个测试
```bash
# 通过 ID 运行特定测试用例
ptest case run <test_case_id>

# 使用 run 命令的备选方式
p run <test_case_id>

# 仅运行失败的测试
p run failed
```

### 开发命令
```bash
# 目前没有正式的测试套件 - 测试通过框架本身运行
# 要测试框架，创建测试环境并运行测试用例：
p init --path ./dev_test
p case add dev_test '{"type": "unit", "description": "Framework test"}'
p case run dev_test
```

## 代码风格指南

### 导入组织
- 使用 `isort` 风格的导入：标准库 → 第三方库 → 本地导入
- 在导入组之间使用空行分隔
- 对本地模块使用绝对导入：`from .utils import setup_logging`
- 避免通配符导入（`from module import *`）

```python
# 标准库导入
import os
import sys
import json
from pathlib import Path
from typing import Dict, List, Any, Optional

# 第三方库导入（当前未使用）

# 本地导入
from .utils import setup_logging
from .config import load_config
```

### 类型提示
- 在所有函数签名和类属性中一致地使用类型提示
- 使用 `from typing import` 导入复杂类型：`Dict`、`List`、`Optional`、`Union`
- 使用返回类型注解：`-> str`、`-> bool`、`-> None`
- 对于类属性，在类体中使用类型注解

```python
def install(self, params: Dict[str, Any] = {}) -> str:
    """使用给定参数安装对象。"""
    pass

class Example:
    name: str
    status: str = 'stopped'
```

### 命名约定
- **类名**：PascalCase（例如 `ObjectManager`、`BaseManagedObject`）
- **函数/方法名**：snake_case（例如 `init_environment`、`setup_logging`）
- **变量名**：snake_case（例如 `test_path`、`config_file`）
- **常量名**：UPPER_SNAKE_CASE（例如 `DEFAULT_CONFIG`、`MAX_TIMEOUT`）
- **私有方法**：以下划线为前缀（例如 `_validate_params`）

### 错误处理
- 使用特定的异常类型：`ValueError`、`FileNotFoundError`、`json.JSONDecodeError`
- 返回带 ✗ 前缀的格式化错误消息表示失败
- 返回带 ✓ 前缀的格式化成功消息表示成功
- 对外部操作使用 try/except 块（文件 I/O、子进程）

```python
try:
    data = json.loads(args.data)
except json.JSONDecodeError:
    print_colored("✗ 测试用例数据的 JSON 格式无效", 91)
    return

if name not in self.objects:
    return f"✗ 对象 '{name}' 不存在"
```

### 日志记录
- 使用框架的日志记录器：`self.env_manager.logger.info()`
- 记录重要操作：对象生命周期、测试执行、错误
- 使用适当的日志级别：`INFO` 用于正常操作，`ERROR` 用于失败

### 文件结构
- 遵循现有的模块化结构，为不同关注点设置单独的管理器
- 使用 `__init__.py` 文件进行包导入
- 将相关功能保持在同一模块中（例如，所有对象管理在 `objects/` 中）

### 文档字符串和注释
- 为所有类和公共方法使用文档字符串
- 遵循现有的文档字符串风格（简单描述）
- 使用 TODO 注释进行未来改进，包含具体细节

```python
def install(self, params: Dict[str, Any] = {}) -> str:
    """使用给定参数安装对象。"""
    # TODO: 添加参数验证
    pass
```

### 彩色输出
- 使用实用函数进行彩色终端输出
- 从 `utils` 导入：`get_colored_text`、`print_colored`
- 使用一致的颜色代码：92（绿色）表示成功，91（红色）表示错误，94（蓝色）表示信息

```python
from ..utils import get_colored_text, print_colored

print_colored(f"✓ 测试用例 '{case_id}' 已添加", 92)
result = f"{get_colored_text('通过', 92)} ({duration:.2f}s)"
```

### 配置
- 使用 `config.py` 中的集中配置系统
- 使用 `load_config()` 函数加载配置
- 使用 `DEFAULT_CONFIG` 获取默认值
- 以 JSON 格式存储配置

### CLI 结构
- 遵循现有的 CLI 模式，使用子命令
- 使用 `argparse` 进行命令行解析
- 提供有用的描述和示例
- 支持长（`ptest`）和短（`p`）命令别名

### 测试模式
- 框架本身就是测试工具 - 测试通过 `CaseManager` 管理
- 测试用例通过字符串 ID 标识
- 测试结果通过 `TestCaseResult` 对象跟踪
- 使用现有的模拟模式进行测试执行，直到实现真实的测试逻辑

### 中文注释
- 代码库包含中文注释和变量名
- 与现有中文文档保持一致
- 在已建立的地方对用户面向的消息和描述使用中文

## 开发说明

- 框架使用模块化架构，为不同关注点设置单独的管理器
- 环境管理由 `EnvironmentManager` 处理
- 对象通过 `ObjectManager` 管理，具有特定的对象类型
- 测试用例由 `CaseManager` 管理，具有结果跟踪
- 报告由 `ReportGenerator` 以 HTML 或 JSON 格式生成
- 代码库正在积极开发中，有许多 TODO 用于未来改进
- 当前测试执行是模拟的 - 真实测试逻辑实现待定