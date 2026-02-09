# -*- coding: utf-8 -*-
# ptest Mock服务模块 / ptest Mock Service Module
#
# 版权所有 (c) 2026 ptest开发团队
# Copyright (c) 2026 ptest Development Team
#
# 许可证: MIT
# License: MIT

"""
ptest Mock服务模块 / ptest Mock Service Module

提供轻量级Mock服务器功能，用于模拟API响应，支持条件匹配和请求历史记录。
Provides lightweight mock server functionality for simulating API responses,
with condition matching and request history tracking.

主要功能 / Main Features:
    - 动态路由配置
    - 条件响应匹配
    - 请求历史记录
    - 并发请求处理
    - CLI集成

示例 / Example:
    >>> from ptest.mock import MockServer, MockRoute
    >>> server = MockServer(name="payment", port=8081)
    >>> server.add_route("/api/pay", "POST", {"status": "success"})
    >>> server.start()
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core import get_logger

logger = get_logger("mock")


@dataclass
class MockRoute:
    """Mock路由定义 / Mock route definition"""

    path: str
    method: str
    response: dict[str, Any]
    when: dict[str, Any] | None = None
    route_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict[str, Any]:
        """转换为字典 / Convert to dictionary"""
        return {
            "route_id": self.route_id,
            "path": self.path,
            "method": self.method,
            "response": self.response,
            "when": self.when,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MockRoute:
        """从字典创建 / Create from dictionary"""
        route = cls(
            path=data.get("path", "/"),
            method=data.get("method", "GET"),
            response=data.get("response", {}),
            when=data.get("when"),
        )
        route.route_id = data.get("route_id", route.route_id)
        return route


@dataclass
class MockRequest:
    """Mock请求记录 / Mock request record"""

    method: str
    path: str
    headers: dict[str, str]
    body: Any
    timestamp: float = field(default_factory=time.time)
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict[str, Any]:
        """转换为字典 / Convert to dictionary"""
        return {
            "request_id": self.request_id,
            "method": self.method,
            "path": self.path,
            "headers": self.headers,
            "body": self.body,
            "timestamp": self.timestamp,
        }


@dataclass
class MockConfig:
    """Mock服务器配置 / Mock server configuration"""

    name: str
    port: int = 8080
    host: str = "127.0.0.1"
    routes: list[MockRoute] = field(default_factory=list)
    request_history_limit: int = 1000

    def to_dict(self) -> dict[str, Any]:
        """转换为字典 / Convert to dictionary"""
        return {
            "name": self.name,
            "port": self.port,
            "host": self.host,
            "routes": [route.to_dict() for route in self.routes],
            "request_history_limit": self.request_history_limit,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MockConfig:
        """从字典创建 / Create from dictionary"""
        routes_data = data.get("routes", [])
        return cls(
            name=data.get("name", "mock_server"),
            port=data.get("port", 8080),
            host=data.get("host", "127.0.0.1"),
            routes=[MockRoute.from_dict(route) for route in routes_data],
            request_history_limit=data.get("request_history_limit", 1000),
        )


class MockServer:
    """Mock服务器 / Mock server"""

    def __init__(self, config: MockConfig):
        """初始化Mock服务器 / Initialize mock server"""
        self.config = config
        self._running = False
        self._server_thread: threading.Thread | None = None
        self._request_history: list[MockRequest] = []
        self._history_lock = threading.Lock()
        self._app = None

    def add_route(
        self,
        path: str,
        method: str,
        response: dict[str, Any],
        when: dict[str, Any] | None = None,
    ) -> str:
        """
        添加Mock路由 / Add mock route

        Args:
            path: 路由路径 / Route path (e.g., "/api/users")
            method: HTTP方法 / HTTP method (GET, POST, PUT, DELETE, etc.)
            response: 响应配置 / Response configuration
            when: 条件匹配 / Condition matching (optional)

        Returns:
            路由ID / Route ID
        """
        route = MockRoute(
            path=path,
            method=method.upper(),
            response=response,
            when=when,
        )
        self.config.routes.append(route)
        logger.info(f"添加Mock路由: {method} {path} / Added mock route")
        return route.route_id

    def remove_route(self, route_id: str) -> bool:
        """移除Mock路由 / Remove mock route"""
        for i, route in enumerate(self.config.routes):
            if route.route_id == route_id:
                self.config.routes.pop(i)
                logger.info(f"移除Mock路由: {route_id} / Removed mock route")
                return True
        logger.warning(f"路由不存在: {route_id} / Route not found")
        return False

    def find_matching_route(
        self, path: str, method: str, headers: dict[str, str], body: Any
    ) -> MockRoute | None:
        """
        查找匹配的路由 / Find matching route

        根据路径、方法和条件匹配查找最合适的路由。
        Finds the most appropriate route based on path, method, and conditions.
        """
        # 先匹配路径和方法
        matching_routes = [
            r
            for r in self.config.routes
            if self._path_matches(r.path, path) and r.method == method.upper()
        ]

        if not matching_routes:
            return None

        # 如果有条件匹配，筛选最匹配的
        for route in matching_routes:
            if route.when and self._check_conditions(route.when, headers, body):
                return route

        # 返回第一个无条件的匹配路由
        for route in matching_routes:
            if not route.when:
                return route

        return matching_routes[0] if matching_routes else None

    def _path_matches(self, route_path: str, request_path: str) -> bool:
        """检查路径是否匹配 / Check if paths match"""
        # 支持简单的路径参数，如 /users/{id}
        pattern = route_path.replace("{", "(?P<").replace("}", ">[^/]+)")
        pattern = f"^{pattern}$"
        return bool(re.match(pattern, request_path))

    def _check_conditions(
        self, when: dict[str, Any], headers: dict[str, str], body: Any
    ) -> bool:
        """检查条件是否满足 / Check if conditions are met"""
        # 检查headers条件
        if "headers" in when:
            for key, value in when["headers"].items():
                if headers.get(key) != value:
                    return False

        # 检查body条件（简化实现）
        if "body" in when and body:
            condition = when["body"]
            if isinstance(condition, dict):
                for key, value in condition.items():
                    if isinstance(body, dict) and body.get(key) != value:
                        return False

        return True

    def _record_request(
        self, method: str, path: str, headers: dict[str, str], body: Any
    ) -> None:
        """记录请求 / Record request"""
        request = MockRequest(
            method=method,
            path=path,
            headers=headers,
            body=body,
        )

        with self._history_lock:
            self._request_history.append(request)
            # 限制历史记录数量
            if len(self._request_history) > self.config.request_history_limit:
                self._request_history.pop(0)

    def get_request_history(self) -> list[MockRequest]:
        """获取请求历史 / Get request history"""
        with self._history_lock:
            return self._request_history.copy()

    def clear_history(self) -> None:
        """清除请求历史 / Clear request history"""
        with self._history_lock:
            self._request_history.clear()
        logger.info("请求历史已清除 / Request history cleared")

    def start(self, blocking: bool = False) -> None:
        """
        启动Mock服务器 / Start mock server

        Args:
            blocking: 是否阻塞 / Whether to block
        """
        if self._running:
            logger.warning("Mock服务器已在运行 / Mock server already running")
            return

        try:
            from flask import Flask, request, jsonify
        except ImportError:
            raise ImportError(
                "Flask is required for mock server. Install with: pip install flask"
            )

        self._app = Flask(f"mock_{self.config.name}")

        # 只在非DEBUG模式下禁用Flask日志
        # Disable Flask logs only when not in DEBUG mode
        if logger.level > 10:  # DEBUG level is 10
            import logging as std_logging

            std_logging.getLogger("werkzeug").setLevel(std_logging.ERROR)

        @self._app.route("/<path:path>", methods=["GET", "POST", "PUT", "DELETE"])
        def handle_request(path):
            method = request.method
            headers = dict(request.headers)
            body = request.get_json() if request.is_json else request.data.decode()

            # 记录请求
            self._record_request(method, f"/{path}", headers, body)

            # 查找匹配的路由
            route = self.find_matching_route(f"/{path}", method, headers, body)

            if route:
                response_data = route.response
                status_code = response_data.get("status", 200)
                body_data = response_data.get("body", {})

                # 处理模板变量
                if isinstance(body_data, dict):
                    body_data = self._process_template(body_data)

                return jsonify(body_data), status_code
            else:
                return jsonify({"error": "No matching route"}), 404

        @self._app.route("/", methods=["GET", "POST", "PUT", "DELETE"])
        def handle_root():
            return handle_request("")

        self._running = True

        if blocking:
            logger.info(
                f"启动Mock服务器: {self.config.host}:{self.config.port} "
                f"/ Starting mock server"
            )
            self._app.run(
                host=self.config.host,
                port=self.config.port,
                debug=False,
                use_reloader=False,
            )
        else:
            self._server_thread = threading.Thread(
                target=self._app.run,
                kwargs={
                    "host": self.config.host,
                    "port": self.config.port,
                    "debug": False,
                    "use_reloader": False,
                },
            )
            self._server_thread.daemon = True
            self._server_thread.start()
            logger.info(
                f"Mock服务器已启动: {self.config.host}:{self.config.port} "
                f"/ Mock server started"
            )

    def _process_template(self, data: dict[str, Any]) -> dict[str, Any]:
        """处理模板变量 / Process template variables"""
        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                # 简单的模板替换
                if "{{uuid}}" in value:
                    value = value.replace("{{uuid}}", str(uuid.uuid4()))
                if "{{timestamp}}" in value:
                    value = value.replace("{{timestamp}}", str(int(time.time())))
            result[key] = value
        return result

    def stop(self) -> None:
        """停止Mock服务器 / Stop mock server"""
        if not self._running:
            return

        self._running = False

        # Flask没有直接的停止方法，这里只是标记状态
        # 实际停止需要更复杂的实现（使用Werkzeug的shutdown路由）

        logger.info("Mock服务器已停止 / Mock server stopped")

    def is_running(self) -> bool:
        """检查服务器是否运行 / Check if server is running"""
        return self._running

    def save_config(self, file_path: Path) -> None:
        """保存配置到文件 / Save configuration to file"""
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.config.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info(f"配置已保存: {file_path} / Configuration saved")

    @classmethod
    def load_config(cls, file_path: Path) -> MockServer:
        """从文件加载配置 / Load configuration from file"""
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        config = MockConfig.from_dict(data)
        return cls(config)
