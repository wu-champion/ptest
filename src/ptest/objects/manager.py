# ptest/ptest/objects/manager.py - 修复版本

import os
from pathlib import Path
from typing import Dict, Any, Optional, TYPE_CHECKING

# 导入所有对象类型
try:
    from . import web as web_module
    from . import service as service_module
    from . import db as db_module
    from . import db_enhanced as db_enhanced_module
except ImportError as e:
    print(f"Warning: Could not import object classes: {e}")

    # Fallback classes
    class WebObject:
        def __init__(self, name, env_manager):
            pass

        def install(self, params=None):
            return (
                f"✗ Web object '{self.name}' not properly configured for installation"
            )

        def start(self):
            return f"✗ Web object '{self.name}' not properly configured for starting"

        def stop(self):
            return f"✗ Web object '{self.name}' not properly configured for stopping"

        def restart(self):
            return f"✗ Web object '{self.name}' not properly configured for restart"

        def delete(self):
            return f"✗ Web object '{self.name}' not properly configured for deletion"

    class ServiceObject:
        def __init__(self, name, env_manager):
            pass

        def install(self, params=None):
            return f"✗ Service object '{self.name}' not properly configured for installation"

        def start(self):
            return (
                f"✗ Service object '{self.name}' not properly configured for starting"
            )

        def stop(self):
            return (
                f"✗ Service object '{self.name}' not properly configured for stopping"
            )

        def restart(self):
            return f"✗ Service object '{self.name}' not properly configured for restart"

        def delete(self):
            return (
                f"✗ Service object '{self.name}' not properly configured for deletion"
            )

    class DBObject:
        def __init__(self, name, env_manager):
            pass

        def install(self, params=None):
            return f"✗ DB object '{self.name}' not properly configured for installation"

        def start(self):
            return f"✗ DB object '{self.name}' not properly configured for starting"

        def stop(self):
            return f"✗ DB object '{self.name}' not properly configured for stopping"

        def restart(self):
            return f"✗ DB object '{self.name}' not properly configured for restart"

        def delete(self):
            return f"✗ DB object '{self.name}' not properly configured for deletion"

    class DatabaseServerObject:
        def __init__(self, name, env_manager):
            pass

        def install(self, params=None):
            return f"✗ Database Server object '{self.name}' not properly configured for installation"

        def start(self):
            return f"✗ Database Server object '{self.name}' not properly configured for starting"

        def stop(self):
            return f"✗ Database Server object '{self.name}' not properly configured for stopping"

        def restart(self):
            return f"✗ Database Server object '{self.name}' not properly configured for restart"

        def delete(self):
            return f"✗ Database Server object '{self.name}' not properly configured for deletion"

    class DatabaseClientObject:
        def __init__(self, name, env_manager):
            pass

        def install(self, params=None):
            return f"✗ Database Client object '{self.name}' not properly configured for installation"

        def start(self):
            return f"✗ Database Client object '{self.name}' not properly configured for starting"

        def stop(self):
            return f"✗ Database Client object '{self.name}' not properly configured for stopping"

        def restart(self):
            return f"✗ Database Client object '{self.name}' not properly configured for restart"

        def delete(self):
            return f"✗ Database Client object '{self.name}' not properly configured for deletion"


from ..utils import get_colored_text


class ObjectManager:
    """对象管理器"""

    def __init__(self, env_manager):
        self.env_manager = env_manager
        self.objects = {}

        # 设置对象类型映射
        self.object_types = {
            "database": {
                "class": db_module.DBObject,
                "client": db_module.DatabaseClientObject,
                "server": db_enhanced_module.DatabaseServerObject,
            },
            "service": service_module.ServiceObject,
            "web": web_module.WebObject,
            "database_server": db_enhanced_module.DatabaseServerObject,
            "database_client": db_enhanced_module.DatabaseClientObject,
            "mongodb": "database_server",  # 偍为MongoDB支持
        }

    def get_object_type(self, name: str) -> Optional[str]:
        """获取对象类型"""
        object_type_map = {
            "mysql": "database",
            "postgresql": "database",
            "postgres": "database",
            "web": "web",
            "nginx": "web",
            "apache": "web",
            "redis": "service",
            "mongodb": "database_server",
        }
        return object_type_map.get(name.lower())

    def create_object(self, obj_type: str, name: str):
        """创建对象实例"""
        if obj_type.lower() not in self.object_types:
            raise ValueError(f"Unknown object type: {obj_type}")

        obj_class = self.object_types[obj_type.lower()]
        obj = obj_class(name, self.env_manager)
        self.objects[name] = obj
        return obj

    def install(self, obj_type: str, name: str, params=None) -> Any:
        """安装对象"""
        try:
            obj = self.create_object(obj_type, name)
            result = obj.install(params)
            if result:
                self.logger.info(f"Successfully installed {name}")
                return f"✓ Installed {name}"
            else:
                self.logger.error(f"Failed to install {name}")
                return f"✗ Failed to install {name}"
        except Exception as e:
            self.logger.error(f"Error installing {name}: {e}")
            return f"✗ Error installing {name}: {e}"

    def start(self, name: str):
        """启动对象"""
        self.env_manager.logger.info(f"Starting test object: {name}")
        if name not in self.objects:
            return f"✗ Object '{name}' does not exist"

        obj = self.objects[name]
        return obj.start()

    def stop(self, name: str):
        """停止对象"""
        self.env_manager.logger.info(f"Stopping test object: {name}")
        if name not in self.objects:
            return f"✗ Object '{name}' does not exist"

        obj = self.objects[name]
        return obj.stop()

    def restart(self, name: str):
        """重启对象"""
        self.env_manager.logger.info(f"Restarting test object: {name}")
        if name not in self.objects:
            return f"✗ Object '{name}' does not exist"

        obj = self.objects[name]
        return obj.restart()

    def uninstall(self, name: str):
        """卸载对象"""
        try:
            obj = self.objects[name]
            result = obj.uninstall()
            if result:
                del self.objects[name]
                self.logger.info(f"Successfully uninstalled {name}")
                return f"✓ Uninstalled {name}"
            else:
                return f"✗ Failed to uninstall {name}"
        except Exception as e:
            self.logger.error(f"Error uninstalling {name}: {e}")
            return f"✗ Error uninstalling {name}"

    def list_objects(self):
        """列出所有对象"""
        if not self.objects:
            return "No objects found"

        result = f"{get_colored_text('Objects:', 95)}\\n"
        for name, obj in self.objects.items():
            result += f"  {name}\\n"
        return result.rstrip()

    def get_object(self, name: str):
        """获取对象"""
        return self.objects.get(name)

    def delete_object(self, name: str):
        """删除对象"""
        try:
            if name in self.objects:
                obj = self.objects[name]
                if hasattr(obj, "delete"):
                    result = obj.delete()
                    if result:
                        del self.objects[name]
                        self.logger.info(f"Successfully deleted {name}")
                        return f"✓ Deleted {name}"
                    else:
                        return f"✗ Failed to delete {name}"
                else:
                    return f"✗ Object '{name}' does not exist or cannot be deleted"
            else:
                return f"✗ Object '{name}' does not exist"

        except Exception as e:
            self.logger.error(f"Error in object operations: {e}")
            return f"✗ Error: {e}"
