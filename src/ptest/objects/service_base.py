# ptest/objects/service_base.py
"""
服务基类 - 定义服务端和客户端的基础接口
"""

from .base import BaseManagedObject
from typing import Dict, Any, Optional, Tuple
from abc import ABC, abstractmethod


class ServiceComponent(ABC):
    """服务组件基类（服务端或客户端）"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.status = "stopped"
        self.process = None

    @abstractmethod
    def start(self) -> Tuple[bool, str]:
        """启动组件"""
        pass

    @abstractmethod
    def stop(self) -> Tuple[bool, str]:
        """停止组件"""
        pass

    @abstractmethod
    def restart(self) -> Tuple[bool, str]:
        """重启组件"""
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """获取组件状态"""
        pass

    @abstractmethod
    def health_check(self) -> Tuple[bool, str]:
        """健康检查"""
        pass


class ServiceServerComponent(ServiceComponent):
    """服务端组件基类"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.host = config.get("host", "localhost")
        self.port = config.get("port", 0)
        self.endpoint = config.get("endpoint", f"{self.host}:{self.port}")

    def get_endpoint(self) -> str:
        """获取服务端点"""
        return self.endpoint

    def get_connection_info(self) -> Dict[str, Any]:
        """获取连接信息"""
        return {
            "host": self.host,
            "port": self.port,
            "endpoint": self.endpoint,
            "protocol": self.config.get("protocol", "tcp"),
        }


class ServiceClientComponent(ServiceComponent):
    """客户端组件基类"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.server_host = config.get("server_host", "localhost")
        self.server_port = config.get("server_port", 0)
        self.server_endpoint = config.get(
            "server_endpoint", f"{self.server_host}:{self.server_port}"
        )

    def connect_to_server(self) -> Tuple[bool, str]:
        """连接到服务端"""
        raise NotImplementedError("Subclasses must implement connect_to_server")

    def disconnect_from_server(self) -> Tuple[bool, str]:
        """断开与服务端的连接"""
        raise NotImplementedError("Subclasses must implement disconnect_from_server")

    def test_connection(self) -> Tuple[bool, str]:
        """测试与服务端的连接"""
        raise NotImplementedError("Subclasses must implement test_connection")
