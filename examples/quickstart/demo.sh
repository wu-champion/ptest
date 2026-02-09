#!/bin/bash
# ptest 快速开始示例一键脚本 / ptest Quick Start One-Click Script
# 此脚本自动化执行完整的测试流程

set -e

echo "======================================"
echo "ptest 快速开始示例"
echo "ptest Quick Start Example"
echo "======================================"
echo ""

# 步骤 1: 初始化测试环境
echo "[步骤 1/6] 初始化测试环境..."
if [ ! -d "./test_env" ]; then
    ptest init --path ./test_env
    echo "   ✓ 测试环境创建成功"
else
    echo "   ✓ 测试环境已存在"
fi
echo ""

# 步骤 2: 运行 API 测试示例
echo "[步骤 2/6] 运行 API 测试示例..."
python examples/quickstart/demo_api.py
echo ""

# 步骤 3: 运行数据库测试示例
echo "[步骤 3/6] 运行数据库测试示例..."
python examples/quickstart/demo_database.py
echo ""

# 步骤 4: 运行所有测试
echo "[步骤 4/6] 运行所有测试..."
ptest run all
echo ""

# 步骤 5: 查看测试报告
echo "[步骤 5/6] 查看测试报告..."
REPORT_FILE=$(find reports -name "ptest_report_*.html" 2>/dev/null | sort -r | head -1)
if [ -n "$REPORT_FILE" ]; then
    echo "   ✓ 报告文件: $REPORT_FILE"
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$REPORT_FILE" 2>/dev/null
    elif command -v open >/dev/null 2>&1; then
        open "$REPORT_FILE" 2>/dev/null
    else
        echo "   请手动打开报告文件"
    fi
else
    echo "   ✗ 报告文件未找到"
fi
echo ""

# 步骤 6: 清理测试环境
echo "[步骤 6/6] 清理测试环境..."
read -p "是否要清理测试环境？(y/N) " -n 1 -r
echo ""
if [[ $REPLY == "y" || $REPLY == "Y" ]]; then
    ptest cleanup
    echo "   ✓ 测试环境清理成功"
else
    echo "   跳过清理"
fi
echo ""

echo "======================================"
echo "示例完成！"
echo "Example Completed!"
echo "======================================"
echo ""
echo "提示: 您可以单独运行示例中的各个功能："
echo "  python examples/quickstart/demo_api.py"
echo "  python examples/quickstart/demo_database.py"
echo ""
