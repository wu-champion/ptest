# Release Notes - ptest v1.3.0

## 发布日期

2026-02-25

## 版本亮点

### 🎉 全新断言系统 (Built-in Assertions)

ptest v1.3.0 带来全新的内置断言系统，让用户无需依赖 pytest/unittest 即可完成测试。

## 新增功能

### 1. 断言系统基础

- **断言基类** (`Assertion`) - 所有断言类型的抽象基类
- **断言结果** (`AssertionResult`) - 标准化的断言结果数据结构
- **断言工厂** (`AssertionFactory`) - 统一的断言创建接口
- **14 种内置断言** - 覆盖常用测试场景

### 2. 内置断言类型

| 断言类型 | 用途 |
|---------|------|
| `equal` / `notequal` | 相等/不等 |
| `contains` | 包含检查 |
| `truthy` / `falsy` | 真假值 |
| `none` / `notnone` | 空值检查 |
| `type` | 类型检查 |
| `statuscode` | HTTP 状态码 |
| `header` | HTTP 响应头 |
| `body` | 响应体 |
| `jsonpath` | JSON 路径 |
| `regex` | 正则匹配 |
| `schema` | JSON Schema |
| `length` | 长度检查 |

### 3. 链式断言

- `AndAssertion` - 所有断言通过才通过
- `OrAssertion` - 任一断言通过就通过
- `NotAssertion` - 反转断言结果
- `ChainBuilder` - 链式构建器

### 4. 断言模板

- `AssertionTemplate` - 可复用的断言模板
- 内置模板：`http_response`, `api_success`
- 支持自定义模板注册

### 5. 性能优化

- 单次断言: < 1ms
- 1000 次断言: < 100ms
- 位置捕获可选启用

## 错误信息增强

失败时自动提供：
- 期望值 / 实际值
- 断言类型
- 调用位置（可选）
- 修复建议

## 文档更新

- 新增 `docs/guides/assertion-guide.md` - 断言使用指南

## 版本更新

- `src/ptest/__init__.py`: 1.0.1 → 1.3.0
- `pyproject.toml`: 1.0.1 → 1.3.0

## 测试覆盖

- 单元测试: 104 个测试用例
- 性能测试: 5 个测试用例
- 全部通过 ✅

## 致谢

感谢所有测试框架的贡献者！
