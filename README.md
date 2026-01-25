# ptest - 综合测试框架

ptest是一个全面的测试框架，用于管理测试环境、测试对象和测试用例。

## 📚 完整文档

完整的文档请访问 [docs/](../docs/) 目录：

- **[用户指南](../docs/user-guide/README.md)** - 快速开始和使用说明
- **[架构文档](../docs/architecture/)** - 系统设计和架构说明  
- **[使用指南](../docs/guides/)** - 详细的使用指南
- **[开发文档](../docs/development/)** - 开发规范和贡献指南
- **[API文档](../docs/api/)** - 接口和数据格式说明

## 🚀 快速开始

### 安装
```bash
pip install .
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