# ptest 断言指南

本文档只描述当前仓库里已经存在且可用的断言接口，不再保留不确定的历史性能结论或旧规划状态。

## 两种使用方式

### 1. 直接使用 `AssertionFactory`

```python
from ptest.assertions import AssertionFactory

assertion = AssertionFactory.create("equal")
result = assertion.assert_value(1, 1)

print(result.passed)
```

### 2. 使用兼容层 `assert_that`

```python
from ptest.assertions import assert_that

assert_that(1).equals(1)
assert_that("hello world").contains("world")
assert_that(True).is_true()
assert_that("value").is_not_none()
```

## 当前内置断言

### 基础断言

- `equal`
- `notequal`
- `contains`
- `length`
- `type`
- `truthy`
- `falsy`
- `none`
- `notnone`

### HTTP / 结构化数据断言

- `statuscode`
- `header`
- `body`
- `jsonpath`
- `regex`
- `schema`

### 常见别名

- `status_code` -> `statuscode`
- `json_path` -> `jsonpath`

## `assert_that` 常用方法

```python
from ptest.assertions import assert_that

assert_that(1).equals(1)
assert_that(1).not_equal(2)
assert_that(["a", "b"]).contains("a")
assert_that("hello").len_is(5)
assert_that("hello").match(r"^hel")
assert_that({"name": "ptest"}).is_instance(dict)
```

兼容层当前常用方法包括：

- `.equals(y)` / `.eq(y)`
- `.not_equal(y)` / `.not_equals(y)` / `.ne(y)`
- `.contains(y)` / `.is_in(y)` / `.in_(y)`
- `.is_true()` / `.is_truthy()`
- `.is_false()` / `.is_falsy()`
- `.is_none()`
- `.not_none()` / `.is_not_none()`
- `.is_instance(type)` / `.is_type(type_name)`
- `.len_is(n)` / `.has_length(n)`
- `.match(pattern)` / `.matches(pattern)`
- `.match_schema(schema)` / `.conforms_to(schema)`

## 异常断言

```python
from ptest.assertions import assert_raises

with assert_raises(ValueError) as ctx:
    raise ValueError("bad input")

print(ctx.exception)
```

## 软断言

```python
from ptest.assertions import SoftAssertions

with SoftAssertions() as soft:
    soft.assert_that(1).equals(2)
    soft.assert_that("a").equals("b")
```

软断言适合一次性收集多个失败结果，再统一报告。

## 断言模板

```python
from ptest.assertions import AssertionTemplate

template = AssertionTemplate.create("api_success")
result = template.assert_value({"code": 0, "message": "ok"}, {"code": 0})
print(result.passed)
```

## 自定义断言

```python
from ptest.assertions import Assertion, AssertionFactory, AssertionRegistry


class MyAssertion(Assertion):
    def assert_value(self, actual, expected=None, **kwargs):
        return self._create_result(actual == expected, actual, expected)


AssertionRegistry.register("my_assertion", MyAssertion)

custom = AssertionFactory.create("my_assertion")
print(custom.assert_value("a", "a").passed)
```

## 失败信息

```python
from ptest.assertions import AssertionFactory

assertion = AssertionFactory.create("equal")
result = assertion.assert_value(1, 2)

print(result.get_error_message())
```

## 当前边界

- 本文档只覆盖仓库中已经存在的断言实现
- 与 pytest / unittest 的兼容层适合渐进迁移，但并不代表完整替代全部生态功能
- 参数化、跳过条件、fixture / mock 等测试框架能力仍应按当前主线能力边界理解

## 相关文档

- API 入口：[../api/README.md](../api/README.md)
- 产品主线：[`../plan/README.md`](../plan/README.md)
