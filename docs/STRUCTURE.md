# 文档目录结构

## docs/ 目录组织原则

`docs/` 只保留两类主文档：

- 内部文档：集中放在 `docs/plan/`
- 对外文档：分为面向用户和面向开发者

## 当前结构

```text
docs/
├── README.md
├── STRUCTURE.md
├── PROJECT_STRUCTURE.md
├── plan/                              # 内部文档，不对外
│   ├── README.md
│   ├── current/                       # 当前正式主线
│   │   ├── requirements/
│   │   ├── mvp/
│   │   ├── plans/
│   │   └── indexes/
│   ├── history/                       # 历史规划资料
│   │   ├── requirements/
│   │   ├── prds/
│   │   ├── designs/
│   │   ├── backlog/
│   │   ├── plans/
│   │   └── reports/
│   ├── sessions/                      # 历史会话与过程记录
│   └── tmp_product_reboot/            # 临时讨论与推导材料
├── user-guide/                        # 对外：用户文档
│   ├── README.md
│   └── basic-usage.md
├── api/                               # 对外：开发者 API 文档
│   ├── README.md
│   ├── python-api-guide.md
│   ├── api-examples.md
│   └── test-data-examples.md
├── architecture/                      # 对外：开发者架构文档
│   ├── README.md
│   ├── system-overview.md
│   ├── ISOLATION_ARCHITECTURE.md
│   └── DATABASE_SEPARATION_ARCHITECTURE_COMPLETE.md
├── development/                       # 对外：开发者工程文档
│   ├── README.md
│   ├── development-guide.md
│   ├── CODING_STANDARDS.md
│   ├── CODE_QUALITY_GUIDE.md
│   ├── CI_CD_GUIDE.md
│   ├── DOCUMENTATION_GUIDE.md
│   └── docker-testing-guide.md
├── guides/                            # 对外：开发者专题指南
│   ├── README.md
│   ├── environment-management.md
│   ├── VIRTUALENV_USER_GUIDE.md
│   ├── assertion-guide.md
│   └── NAMING_CONVENTION.md
└── archived/                          # 对外：历史参考，不作为当前权威说明
    ├── README.md
    └── ...
```

## 归档规则

### 1. `docs/plan/`

以下内容统一进入 `docs/plan/`：

- 当前正式产品主线文档
- 历史规划与历史实现资料
- 历史会话
- 内部整理报告
- 临时讨论与推导材料

### 2. 面向用户

以下内容进入 `docs/user-guide/`：

- 安装说明
- 快速开始
- 基础使用教程
- 用户操作路径说明

### 3. 面向开发者

以下内容进入开发者文档目录：

- `docs/architecture/`: 架构与设计说明
- `docs/development/`: 工程规范、开发流程、质量规则
- `docs/guides/`: 功能专题使用指南
- `docs/api/`: 编程接口和示例

### 4. `docs/archived/`

以下内容进入 `docs/archived/`：

- 已过时但仍需保留的公开文档
- 历史设计稿
- 旧版本说明

## 维护要求

- 新增文档时，先判断是否属于内部研发沉淀；如果是，放入 `docs/plan/`
- 根目录 `docs/README.md` 只做导航，不承载内部研发过程细节
- 每个公开文档目录都应有自己的 `README.md` 作为入口
- 文档结构变更后，需同步更新本文件
