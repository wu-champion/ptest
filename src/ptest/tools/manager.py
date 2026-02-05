# ptest/tools/manager.py
from ..utils import get_colored_text


class ToolObject:
    """工具对象实现"""

    def __init__(self, name: str, env_manager):
        self.name = name
        self.type_name = "tool"
        self.status = "stopped"
        self.installed = False
        self.env_manager = env_manager

    def execute_command(self, cmd, timeout=30):
        """执行系统命令"""
        from ..utils import execute_command

        return execute_command(cmd, timeout, self.env_manager.test_path)

    def install(self, params=None):
        """安装工具"""
        self.env_manager.logger.info(f"Installing tool: {self.name}")
        self.installed = True
        self.status = "installed"
        return f"✓ {get_colored_text('Tool', 92)} '{self.name}' installed"

    def start(self):
        """启动工具"""
        if not self.installed:
            return f"✗ Tool '{self.name}' not installed"
        self.env_manager.logger.info(f"Starting tool: {self.name}")
        self.status = "running"
        return f"✓ {get_colored_text('Tool', 92)} '{self.name}' started"

    def stop(self):
        """停止工具"""
        if self.status != "running":
            return f"✗ Tool '{self.name}' not running"
        self.env_manager.logger.info(f"Stopping tool: {self.name}")
        self.status = "stopped"
        return f"✓ {get_colored_text('Tool', 92)} '{self.name}' stopped"

    def restart(self):
        """重启工具"""
        result = self.stop()
        if "✓" in result:
            return self.start()
        return result

    def uninstall(self):
        """卸载工具"""
        if self.status == "running":
            self.stop()
        self.env_manager.logger.info(f"Removing tool: {self.name}")
        self.installed = False
        self.status = "removed"
        return f"✓ {get_colored_text('Tool', 92)} '{self.name}' uninstalled"


class ToolManager:
    """工具管理器"""

    def __init__(self, env_manager):
        self.env_manager = env_manager
        self.tools = {}

    def install(self, name: str, params=None):
        """安装工具"""
        self.env_manager.logger.info(f"Installing tool: {name}")
        tool = ToolObject(name, self.env_manager)
        result = tool.install(params)
        self.tools[name] = tool
        return result

    def start(self, name: str):
        """启动工具"""
        self.env_manager.logger.info(f"Starting tool: {name}")
        if name not in self.tools:
            return f"✗ Tool '{name}' does not exist"
        return self.tools[name].start()

    def stop(self, name: str):
        """停止工具"""
        self.env_manager.logger.info(f"Stopping tool: {name}")
        if name not in self.tools:
            return f"✗ Tool '{name}' does not exist"
        return self.tools[name].stop()

    def restart(self, name: str):
        """重启工具"""
        self.env_manager.logger.info(f"Restarting tool: {name}")
        if name not in self.tools:
            return f"✗ Tool '{name}' does not exist"
        return self.tools[name].restart()

    def uninstall(self, name: str):
        """卸载工具"""
        self.env_manager.logger.info(f"Uninstalling tool: {name}")
        if name not in self.tools:
            return f"✗ Tool '{name}' does not exist"
        result = self.tools[name].uninstall()
        del self.tools[name]
        return result

    def list_tools(self):
        """列出所有工具"""
        if not self.tools:
            return "No tools found"

        result = f"{get_colored_text('Tools:', 95)}\n"
        for name, tool in self.tools.items():
            status = tool.status.upper()
            color = 92 if status == "RUNNING" else 93 if status == "STOPPED" else 91
            result += f"{get_colored_text('tool', 94)} - {get_colored_text(name, 97)} [{get_colored_text(status, color)}]\n"
        return result.rstrip()
