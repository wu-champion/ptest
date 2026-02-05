# ptest/objects/web.py
from .base import BaseManagedObject
from ..utils import get_colored_text


class WebObject(BaseManagedObject):
    """Web对象实现"""

    def __init__(self, name: str, env_manager):
        super().__init__(name, "web", env_manager)

    def install(self, params=None):
        self.env_manager.logger.info(f"Installing web object: {self.name}")
        self.installed = True
        self.status = "installed"
        return f"✓ {get_colored_text('Web', 92)} object '{self.name}' installed"

    def start(self):
        if not self.installed:
            return f"✗ Web object '{self.name}' not installed"
        self.env_manager.logger.info(f"Starting web object: {self.name}")
        self.status = "running"
        return f"✓ {get_colored_text('Web', 92)} object '{self.name}' started"

    def stop(self):
        if self.status != "running":
            return f"✗ Web object '{self.name}' not running"
        self.env_manager.logger.info(f"Stopping web object: {self.name}")
        self.status = "stopped"
        return f"✓ {get_colored_text('Web', 92)} object '{self.name}' stopped"

    def restart(self):
        result = self.stop()
        if "✓" in result:
            return self.start()
        return result

    def uninstall(self):
        if self.status == "running":
            self.stop()
        self.env_manager.logger.info(f"Removing web object: {self.name}")
        self.installed = False
        self.status = "removed"
        return f"✓ {get_colored_text('Web', 92)} object '{self.name}' uninstalled"
