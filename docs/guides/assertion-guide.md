# ptest 断言系统使用指南

## 概述

ptest 内置断言系统，让用户无需依赖 pytest/unittest 即可完成测试。

## 快速开始

```python
from ptest.assertions import AssertionFactory

# 创建断言
eq = AssertionFactory.create("equal")

# 执行断言
result = eq.assert_value(1, 1)
print(f"Passed: {result.passed}")
```

## 内置断言类型

### 基础断言

| 断言类型 | 用法 | 示例 |
|---------|------|------|
| `equal` | 相等 | `eq.assert_value(1, 1)` |
| `notequal` | 不等 | `neq.assert_value(1, 2)` |
| `contains` | 包含 | `contains.assert_value("hello world", "world")` |
| `length` | 长度 | `length.assert_value("hello", 5)` |

### 真假值断言

| 断言类型 | 用法 | 示例 |
|---------|------|------|
| `truthy` | 真值 | `truthy.assert_value("hello")` |
| `falsy` | 假值 | `falsy.assert_value("")` |
| `none` | 空值 | `none.assert_value(None)` |
| `notnone` | 非空 | `notnone.assert_value("value")` |

### 类型断言

| 断言类型 | 用法 | 示例 |
|---------|------|------|
| `type` | 类型检查 | `type.assert_value("hello", "str")` |

### HTTP 断言

| 断言类型 | 用法 | 示例 |
|---------|------|------|
| `statuscode` | 状态码 | `sc.assert_value(200, 200)` |
| `header` | 响应头 | `header.assert_value(headers, "json", header="content-type")` |
| `body` | 响应体 | `body.assert_value('{"key":"value"}', {"key":"value"})` |
| `jsonpath` | JSON路径 | `jp.assert_value(data, "test", path="name")` |

### 正则与 Schema

| 断言类型 | 用法 | 示例 |
|---------|------|------|
| `regex` | 正则匹配 | `regex.assert_value("hello", r"^hel")` |
| `schema` | JSON Schema | `schema.assert_value({"a":1}, None, schema={"type":"object"})` |

## 链式断言

```python
from ptest.assertions import AssertionFactory, AndAssertion, OrAssertion, NotAssertion

# AND - 所有断言通过才通过
and_assert = AndAssertion(eq, truthy)
result = and_assert.assert_value(42, 42)

# OR - 任一断言通过就通过
or_assert = OrAssertion(eq, truthy)
result = or_assert.assert_value(42, 43)  # truthy 通过

# NOT - 反转结果
not_assert = NotAssertion(eq)
result = not_assert.assert_value(1, 2)  # 1!=2 失败，NOT 后通过
```

## 断言模板

```python
from ptest.assertions import AssertionTemplate

# 使用内置模板
template = AssertionTemplate.create("api_success")
result = template.assert_value({"code": 0, "message": "ok"}, {"code": 0})

# 注册自定义模板
def my_template(actual, expected=None, **kwargs):
    ...

AssertionTemplate.register("my_template", my_template)
```

## 自定义断言

```python
from ptest.assertions import Assertion, AssertionResult, AssertionRegistry

class MyAssertion(Assertion):
    def assert_value(self, actual, expected=None, **kwargs):
        passed = actual == expected
        return self._create_result(passed, actual, expected)

# 注册
AssertionRegistry.register("my_assertion", MyAssertion)

# 使用
my = AssertionFactory.create("my_assertion")
```

## 错误信息

失败时获取详细信息：

```python
result = eq.assert_value(1, 2)
print(result.get_error_message())
# 输出: 断言失败: None | 类型: EqualAssertion | 期望: 2 | 实际: 1 | 建议: 检查比较的值

# 启用位置捕获（性能开销）
result = eq.assert_value(1, 2, capture_location=True)
```

## 性能

- 单次断言: < 1ms
- 1000 次断言: < 100ms

位置捕获默认关闭以保证性能，需要时通过 `capture_location=True` 启用。
