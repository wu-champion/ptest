# 示例 3: Mock 服务使用

本示例展示如何使用 Mock 服务进行测试，避免依赖外部服务。

## 前置要求

```bash
# 安装 Mock 服务库
pip install requests-mock
```

## 运行方式

```bash
# 运行测试
pytest cases/ -v
```

## 测试用例说明

### test_payment
- 描述: 测试支付流程（使用 Mock）
- 类型: API + Mock 测试
- 演示: 如何模拟外部支付接口

## Mock 配置

```yaml
mock_config:
  - name: payment_service
    url: https://api.payment.com/*
    response:
      status: 200
      body:
        transaction_id: "TXN_12345"
        status: "success"
```

## 下一步

- 示例 4: 数据生成与参数化
- 示例 5: 测试套件组织
