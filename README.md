# ptest - 综合测试框架

> **注意**: v1.2+ 包名已改为 `ptestx`，安装命令: `pip install ptestx`

ptest 是一个全面的测试框架，用于管理测试环境、测试对象、测试用例、测试套件和测试数据。

## 📚 完整文档

完整的文档请访问 [docs/](../docs/) 目录：

- **[用户指南](./docs/user-guide/README.md)** - 快速开始和使用说明
- **[架构文档](./docs/architecture/)** - 系统设计和架构说明  
- **[使用指南](./docs/guides/)** - 详细的使用指南
- **[开发文档](./docs/development/)** - 开发规范和贡献指南
- **[API文档](./docs/api/)** - 接口和数据格式说明

## 🚀 快速开始

### 安装
```bash
pip install ptestx
```

### 快速开始示例
```bash
# 查看快速开始示例
ls examples/

# 运行基础 API 测试示例
cd examples/01_basic_api_test
pytest ...
```

### 初始化测试环境
```bash
ptest init --path /home/test/
```

### 管理测试对象
以Mysql为例
```bash
# 安装MySQL对象
ptest obj install mysql my_mysql_db --version 9.9.9

# 启动MySQL对象
ptest obj start my_mysql_db

# 列出所有对象
ptest obj list
```

### 管理测试用例
```bash
# 添加测试用例
ptest case add mysql_connection_test '{"type": "connection", "description": "Test MySQL connection"}'

# 运行特定测试用例
ptest case run mysql_connection_test

# 运行所有测试用例
ptest run all

# 并行执行
ptest case run all --parallel --workers 4
```

### 测试套件管理 (v1.2+)
```bash
# 创建套件
ptest suite create my_suite

# 运行套件
ptest suite run my_suite

# 并行执行
ptest suite run my_suite --parallel --workers 4

# 失败停止
ptest suite run my_suite --stop-on-failure

# 预览模式
ptest suite run my_suite --dry-run
```

### Mock 服务管理 (v1.2+)
```bash
# 启动 Mock 服务
ptest mock start --config mock_config.yaml

# 停止 Mock 服务
ptest mock stop --name payment_gateway

# 查看 Mock 列表
ptest mock list
```

### 数据生成 (v1.2+)
```bash
# 生成测试数据
ptest data generate user --count 100

# 生成 SQL INSERT 语句
ptest data generate user --format sql --table users --dialect mysql

# 查看支持的数据类型
ptest data types
```

### API 契约管理 (v1.2+)
```bash
# 导入 OpenAPI 契约
ptest contract import --source https://api.example.com/openapi.json

# 查看契约列表
ptest contract list

# 验证契约
ptest contract validate my_contract
```

### 生成报告
```bash
# 生成HTML报告
ptest report --format html

# 生成JSON报告
ptest report --format json
```

### 查看状态
```bash
ptest status
```

### 命令别名
同时提供了```p```作为简写命令：
```bash
p init --path /home/test/
p obj install mysql my_mysql_db
p run all
```

## 📖 更多信息

查看 [docs/](../docs/) 目录获取完整的文档，包括：

- 详细的架构设计文档
- 数据库配置和使用指南
- 测试执行引擎说明
- 开发规范和贡献指南
- API 接口文档

---

*ptest - 综合测试框架，让测试变得简单而强大！*