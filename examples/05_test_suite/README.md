# 示例 5: 测试套件组织

本示例展示如何组织和管理测试套件。

## 运行方式

```bash
# 运行整个套件
ptest suite run regression_suite

# 运行单个用例
ptest run cases/test_case_1.yaml
```

## 套件结构

```
05_test_suite/
├── suites/
│   └── regression_suite.yaml    # 套件定义
├── cases/
│   ├── test_case_1.yaml         # 测试用例 1
│   ├── test_case_2.yaml         # 测试用例 2
│   └── test_case_3.yaml         # 测试用例 3
└── ptest_config.yaml
```

## 套件配置说明

### 1. 基础套件配置
```yaml
suite:
  name: regression_suite
  description: 回归测试套件
```

### 2. 用例选择
```yaml
cases:
  - cases/test_case_1.yaml
  - cases/test_case_2.yaml
```

### 3. 并行配置
```yaml
execution:
  parallel: true
  workers: 4
```

### 4. 标签过滤
```yaml
tags:
  include: [smoke, regression]
  exclude: [slow]
```

## 下一步

完成所有示例后，建议:
- 阅读完整文档: docs/
- 查看 API 参考: docs/api/
- 参与贡献: CONTRIBUTING.md
