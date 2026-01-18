# ptest/objects/db.py
from .base import BaseManagedObject
from ..utils import get_colored_text

class DBObject(BaseManagedObject):
    """通用数据库对象实现"""
    def __init__(self, name: str, env_manager):
        super().__init__(name, 'database', env_manager)

    def install(self, params=None):
        self.env_manager.logger.info(f"Installing database object: {self.name}")
        self.installed = True
        self.status = 'installed'
        return f"✓ {get_colored_text('Database', 92)} object '{self.name}' installed"
        
    def start(self):
        if not self.installed:
            return f"✗ Database object '{self.name}' not installed"
        self.env_manager.logger.info(f"Starting database object: {self.name}")
        self.status = 'running'
        return f"✓ {get_colored_text('Database', 92)} object '{self.name}' started"
        
    def stop(self):
        if self.status != 'running':
            return f"✗ Database object '{self.name}' not running"
        self.env_manager.logger.info(f"Stopping database object: {self.name}")
        self.status = 'stopped'
        return f"✓ {get_colored_text('Database', 92)} object '{self.name}' stopped"
        
    def restart(self):
        result = self.stop()
        if "✓" in result:
            return self.start()
        return result
        
    def uninstall(self):
        if self.status == 'running':
            self.stop()
        self.env_manager.logger.info(f"Removing database object: {self.name}")
        self.installed = False
        self.status = 'removed'
        return f"✓ {get_colored_text('Database', 92)} object '{self.name}' uninstalled"