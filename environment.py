# ptest/environment.py
from pathlib import Path
from .utils import setup_logging
from .config import load_config, DEFAULT_CONFIG

class EnvironmentManager:
    """环境管理器"""
    
    def __init__(self) -> None:
        self.test_path = None
        self.log_dir = None
        self.report_dir = None
        self.config = DEFAULT_CONFIG
        self.logger = None
        
    def init_environment(self, path) -> str:
        """初始化测试环境"""
        self.test_path = Path(path).resolve()
        if not self.test_path.exists():
            self.test_path.mkdir(parents=True, exist_ok=True)
            
        # 创建必要的目录结构
        dirs = ['objects', 'tools', 'cases', 'logs', 'reports', 'data', 'scripts']
        for dir_name in dirs:
            (self.test_path / dir_name).mkdir(exist_ok=True)
            
        self.log_dir = self.test_path / 'logs'
        self.report_dir = self.test_path / 'reports'
        
        # 设置日志
        self.logger = setup_logging(self.log_dir)
        
        # 创建默认配置文件
        config_file = self.test_path / 'ptest_config.json'
        if not config_file.exists():
            from .config import DEFAULT_CONFIG
            import json
            with open(config_file, 'w') as f:
                json.dump(DEFAULT_CONFIG, f, indent=2)
                
        self.config = load_config(config_file)
        
        self.logger.info(f"Test environment initialized at: {self.test_path}")
        return f"✓ Test environment initialized at: {self.test_path}"
    
    def get_env_status(self):# -> dict[str, Any] | Literal['Environment not initialized']:
        """获取环境状态"""
        if not self.test_path:
            return "Environment not initialized"
        
        stats = {
            "path": str(self.test_path),
            "objects": len(list((self.test_path / 'objects').glob('*'))) if (self.test_path / 'objects').exists() else 0,
            "tools": len(list((self.test_path / 'tools').glob('*'))) if (self.test_path / 'tools').exists() else 0,
            "cases": len(list((self.test_path / 'cases').glob('*'))) if (self.test_path / 'cases').exists() else 0,
            "reports": len(list((self.test_path / 'reports').glob('*'))) if (self.test_path / 'reports').exists() else 0,
        }
        return stats


