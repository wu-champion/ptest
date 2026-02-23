# 示例 1: 基础 API 测试

本示例展示如何使用 ptest 进行最基本的 REST API 测试。

## 运行方式

```bash
# 运行测试
pytest cases/ -v

# 或使用 ptest CLI
ptest run cases/test_health_check.yaml
```

## 测试用例说明

### test_health_check
- 描述: 测试 httpbin.org 健康检查接口
- 类型: API 测试
- 验证: HTTP 状态码为 200，响应包含正确的 URL

## 预期输出

```
PASSED: test_health_check
  - Status Code: 200 ✓
  - Response URL: https://httpbin.org/get ✓
```

## 扩展练习

1. 修改 `cases/test_health_check.yaml` 测试其他 HTTP 方法 (POST, PUT, DELETE)
2. 添加更多的断言验证响应内容
3. 测试不同的 API 端点

## 下一步

完成本示例后，可以继续学习:
- 示例 2: 数据库测试
- 示例 3: Mock 服务使用
