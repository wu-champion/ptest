"""
单元测试模块

包含对各个模块的单元测试，确保基本功能正确性。
"""

# 导入路径配置
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
