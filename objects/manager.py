# ptest/objects/manager.py
from pathlib import Path
# from .mysql import MySQLObject
from .web import WebObject
from .service import ServiceObject
from .db import DBObject
from ..utils import get_colored_text

class ObjectManager:
    """被测对象管理器"""
    
    def __init__(self, env_manager):
        self.env_manager = env_manager
        self.objects = {}
        self.object_types = {
            # 'mysql': MySQLObject,
            'web': WebObject,
            'service': ServiceObject,
            'db': DBObject
        }
        
    def create_object(self, obj_type: str, name: str):
        """创建对象实例"""
        if obj_type.lower() not in self.object_types:
            raise ValueError(f"Unknown object type: {obj_type}")
            
        obj_class = self.object_types[obj_type.lower()]
        obj = obj_class(name, self.env_manager)
        self.objects[name] = obj
        return obj
        
    def install(self, obj_type: str, name: str, params=None):
        """安装被测对象"""
        self.env_manager.logger.info(f"Installing test object: {name} ({obj_type})")
        obj = self.create_object(obj_type, name)
        result = obj.install(params)
        return result
        
    def start(self, name: str):
        """启动被测对象"""
        self.env_manager.logger.info(f"Starting test object: {name}")
        if name not in self.objects:
            return f"✗ Object '{name}' does not exist"
        return self.objects[name].start()
        
    def stop(self, name: str):
        """停止被测对象"""
        self.env_manager.logger.info(f"Stopping test object: {name}")
        if name not in self.objects:
            return f"✗ Object '{name}' does not exist"
        return self.objects[name].stop()
        
    def restart(self, name: str):
        """重启被测对象"""
        self.env_manager.logger.info(f"Restarting test object: {name}")
        if name not in self.objects:
            return f"✗ Object '{name}' does not exist"
        return self.objects[name].restart()
        
    def uninstall(self, name: str):
        """卸载被测对象"""
        self.env_manager.logger.info(f"Uninstalling test object: {name}")
        if name not in self.objects:
            return f"✗ Object '{name}' does not exist"
        result = self.objects[name].uninstall()
        del self.objects[name]
        return result
        
    def list_objects(self):
        """列出所有对象"""
        if not self.objects:
            return "No objects found"
        
        result = f"{get_colored_text('Test Objects:', 95)}\n"
        for name, obj in self.objects.items():
            status = obj.status.upper()
            color = 92 if status == "RUNNING" else 93 if status == "STOPPED" else 91
            type_color = 94 if obj.type_name == 'mysql' else 96
            result += f"{get_colored_text(obj.type_name, type_color)} - {get_colored_text(name, 97)} [{get_colored_text(status, color)}]\n"
        return result.rstrip()