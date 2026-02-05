# ptest/objects/base.py
from abc import ABC, abstractmethod
# from ..environment import EnvironmentManager


class BaseManagedObject(ABC):
    """被测对象基类"""

    def __init__(
        self,
        name: str,
        type_name: str,
        env_manager,  # 类型为 EnvironmentManager
    ) -> None:
        self.name = name
        self.type_name = type_name
        self.status = "stopped"
        self.installed = False
        self.env_manager = env_manager

    @abstractmethod
    def install(self, params: object) -> object:
        """安装对象"""
        pass

    @abstractmethod
    def start(self) -> object:
        """启动对象"""
        pass

    @abstractmethod
    def stop(self) -> object:
        """停止对象"""
        pass

    @abstractmethod
    def restart(self) -> object:
        """重启对象"""
        pass

    @abstractmethod
    def uninstall(self) -> object:
        """卸载对象"""
        pass
