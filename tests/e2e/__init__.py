"""
端到端测试模块

包含完整用户场景的端到端测试。
"""

# 导入路径配置
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
