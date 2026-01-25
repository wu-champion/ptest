# 文档目录结构

## 📁 docs/ 目录组织

```
docs/
├── README.md                           # 📖 文档总览和导航
├── STRUCTURE.md                        # 📂 文档结构说明
├── user-guide/                         # 👥 用户指南
│   ├── README.md                      # 快速开始指南
│   └── basic-usage.md                 # 基础使用教程
│   ├── advanced-features.md            # 高级功能指南
│   └── faq.md                         # 常见问题解答
├── architecture/                       # 🏗️ 架构设计文档
│   ├── system-overview.md              # 系统架构总览
│   ├── environment-isolation.md         # 环境隔离架构
│   └── ISOLATION_ARCHITECTURE.md        # 隔离架构设计详情
├── guides/                             # 📋 使用指南
│   ├── environment-management.md        # 环境管理指南
│   ├── test-case-writing.md             # 测试用例编写指南
│   ├── object-management.md             # 对象管理指南
│   └── report-generation.md            # 报告生成指南
├── development/                        # 🛠️ 开发文档
│   ├── development-guide.md             # 开发指南
│   ├── requirements.md                 # 需求规格说明书
│   ├── implementation-plans/           # 实现计划
│   │   ├── ENV-001_DETAILED_REQUIREMENTS.md
│   │   └── ENV-001_IMPLEMENTATION_PLAN.md
│   ├── progress-reports/               # 开发进度报告
│   │   └── WEEK1_COMPLETION_REPORT.md
│   └── PYTHON_API_IMPLEMENTATION.md    # API实现报告
├── api/                                # 📔 API 文档
│   ├── python-api.md                   # Python API 参考文档
│   ├── python-api-guide.md              # API 使用指南
│   ├── api-examples.md                 # API 使用示例
│   ├── cli-commands.md                 # CLI 命令参考
│   └── README.md                       # 测试数据示例
└── archived/                           # 🗃️ 归档文档
    ├── README.md                       # 归档文档索引
    ├── prd.md                          # 旧需求规格书
    ├── AGENTS.md                       # 开发代理指南(中文)
    ├── AGENTS_EN.md                    # 开发代理指南(英文)
    ├── DATABASE_ARCHITECTURE_REFACTOR.md
    ├── DATABASE_SEPARATION_ARCHITECTURE_COMPLETE.md
    ├── DATABASE_SERVER_CLIENT_SEPARATION.md
    ├── UNIVERSAL_DATABASE_CONNECTOR.md
    ├── TEST_DIRECTORY_RESTRUCTURE.md
    └── TEST_EXECUTION_README.md
```

## 🎯 分类说明

### 👥 用户指南 (user-guide/)
面向最终用户的使用文档，包括：
- 框架介绍
- 快速开始指南
- 基本使用方法
- 常见问题解答

### 🏗️ 架构文档 (architecture/) 
面向架构师和高级开发者的设计文档，包括：
- 系统架构设计
- 数据库架构重构
- 服务端/客户端分离设计
- 通用连接器架构

### 📋 使用指南 (guides/)
面向开发者的详细使用指南，包括：
- 测试目录组织
- 测试执行引擎使用
- 最佳实践
- 配置指南

### 🛠️ 开发文档 (development/)
面向框架开发者的技术文档，包括：
- 开发规范和指南
- 代码风格指南
- 需求规格说明
- 贡献指南

### 📔 API 文档 (api/)
面向程序员的接口文档，包括：
- API 接口说明
- 数据格式规范
- 示例代码
- 测试数据格式

## 🔄 维护指南

### 添加新文档
1. 确定文档分类
2. 在对应目录下创建文件
3. 更新本目录结构说明
4. 更新主 README.md 导航

### 文档命名规范
- 使用英文文件名，单词间用下划线分隔
- 文件名应清晰表达文档内容
- 避免使用特殊字符和空格

### 文档格式规范
- 使用 Markdown 格式
- 遵循统一的标题层级
- 包含适当的目录和导航链接