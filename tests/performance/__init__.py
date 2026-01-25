"""
性能测试模块

包含系统性能、响应时间、吞吐量等性能测试。
"""

# 导入路径配置
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
