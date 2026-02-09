# ptest 快速开始示例 / ptest Quick Start Example

快速开始指南，帮助您在5分钟内上手 ptest 测试框架。

---

## 快速开始步骤 / Quick Start Steps

### 1. 初始化测试环境 / Initialize Test Environment

```bash
# 初始化测试环境
ptest init --path ./my_test_env
```

### 2. 运行 API 测试示例 / Run API Test Example

```bash
# 切换到示例目录
cd examples/quickstart

# 运行 API 测试示例
python demo_api.py
```

### 3. 运行数据库测试示例 / Run Database Test Example

```bash
# 切换到示例目录
cd examples/quickstart

# 运行数据库测试示例
python demo_database.py
```

### 4. 一键运行完整流程 / Run Complete Workflow

```bash
# 运行一键脚本
bash demo.sh
```

---

## 示例说明 / Example Description

### API 测试示例 / API Test Example

文件: `demo_api.py`

演示如何使用 ptest 进行 REST API 测试，包括：
- 创建测试用例
- 执行测试
- 查看测试结果

### 数据库测试示例 / Database Test Example

文件: `demo_database.py`

演示如何使用 ptest 进行数据库测试，包括：
- 安装 MySQL 测试对象
- 创建数据库测试用例
- 执行测试
- 清理测试环境

### 一键脚本 / One-Click Script

文件: `demo.sh`

自动化执行完整测试流程：
1. 初始化测试环境
2. 安装 MySQL 测试对象
3. 创建并执行测试用例
4. 查看测试报告
5. 清理测试环境

---

## 配置文件 / Configuration File

文件: `test_config.yaml`

示例配置文件，包含：
- 日志配置
- 报告配置
- 测试执行配置

---

## 预期输出 / Expected Output

运行示例后，您应该看到：
- 测试环境创建成功
- 测试用例执行成功
- 测试报告生成成功
- 测试环境清理成功

---

## 常见问题 / FAQ

### Q: 如何修改测试用例？
A: 编辑 `demo_api.py` 或 `demo_database.py` 中的测试用例定义。

### Q: 如何查看详细日志？
A: 使用 `--debug` 或 `--verbose` 参数：
   ```bash
   ptest --debug run all
   ```

### Q: 测试报告在哪里？
A: 默认在 `./reports/` 目录，可在配置文件中修改。

---

## 下一步 / Next Steps

- 查看 API 文档: `docs/api/`
- 查看使用指南: `docs/user-guide/`
- 查看更多示例: `examples/`
