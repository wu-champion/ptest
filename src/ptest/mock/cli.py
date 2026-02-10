# -*- coding: utf-8 -*-
# ptest Mock CLI 命令 / ptest Mock CLI Commands
#
# 版权所有 (c) 2026 ptest开发团队
# Copyright (c) 2026 ptest Development Team
#
# 许可证: MIT
# License: MIT

"""
ptest Mock CLI 命令 / ptest Mock CLI Commands

提供Mock服务器的命令行管理接口。
Provides command-line interface for mock server management.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..utils import print_colored, get_colored_text
from . import MockServer, MockConfig
from ..core import get_logger

logger = get_logger("mock.cli")

# 全局Mock服务器实例缓存
_mock_servers: dict[str, MockServer] = {}


def setup_mock_subparser(subparsers):
    """设置 mock 子命令 / Setup mock subcommand"""
    mock_parser = subparsers.add_parser(
        "mock", help=get_colored_text("Mock server management", 96)
    )
    mock_subparsers = mock_parser.add_subparsers(
        dest="mock_action", help="Mock actions"
    )

    # start 子命令
    start_parser = mock_subparsers.add_parser("start", help="Start mock server")
    start_parser.add_argument("name", help="Server name")
    start_parser.add_argument("--config", help="Configuration file path")
    start_parser.add_argument("--port", type=int, default=8080, help="Server port")
    start_parser.add_argument(
        "--blocking", action="store_true", help="Run in blocking mode"
    )

    # stop 子命令
    stop_parser = mock_subparsers.add_parser("stop", help="Stop mock server")
    stop_parser.add_argument("name", help="Server name")

    # status 子命令
    status_parser = mock_subparsers.add_parser("status", help="Check server status")
    status_parser.add_argument("name", help="Server name")

    # logs 子命令
    logs_parser = mock_subparsers.add_parser("logs", help="View request logs")
    logs_parser.add_argument("name", help="Server name")
    logs_parser.add_argument(
        "--limit", type=int, default=10, help="Number of logs to show"
    )

    # list 子命令
    mock_subparsers.add_parser("list", help="List all mock servers")

    # add-route 子命令
    route_parser = mock_subparsers.add_parser("add-route", help="Add mock route")
    route_parser.add_argument("name", help="Server name")
    route_parser.add_argument("path", help="Route path")
    route_parser.add_argument("--method", default="GET", help="HTTP method")
    route_parser.add_argument("--response", required=True, help="Response JSON")
    route_parser.add_argument("--when", help="Condition JSON (optional)")

    return mock_parser


def handle_mock_command(args) -> bool:
    """处理 mock 命令 / Handle mock command"""
    if not hasattr(args, "mock_action") or not args.mock_action:
        print_colored(
            "Please specify a mock action (start/stop/status/logs/list/add-route)", 91
        )
        return False

    handlers = {
        "start": lambda: _handle_start(args),
        "stop": lambda: _handle_stop(args),
        "status": lambda: _handle_status(args),
        "logs": lambda: _handle_logs(args),
        "list": lambda: _handle_list(),
        "add-route": lambda: _handle_add_route(args),
    }

    handler = handlers.get(args.mock_action)
    if handler:
        return handler()

    print_colored("Unknown mock action", 91)
    return False


def _handle_start(args) -> bool:
    """处理 start 子命令 / Handle start subcommand"""
    if args.name in _mock_servers:
        print_colored(f"Mock server '{args.name}' is already running", 93)
        return True

    try:
        if args.config:
            config_path = Path(args.config)
            if not config_path.exists():
                print_colored(f"Config file not found: {args.config}", 91)
                return False
            server = MockServer.load_config(config_path)
        else:
            config = MockConfig(name=args.name, port=args.port)
            server = MockServer(config)

        server.start(blocking=args.blocking)
        _mock_servers[args.name] = server

        if args.blocking:
            print_colored(f"Mock server '{args.name}' started (blocking mode)", 92)
        else:
            print_colored(
                f"Mock server '{args.name}' started on port {server.config.port}", 92
            )
        return True

    except ImportError as e:
        print_colored(f"Flask is required: {e}", 91)
        print_colored("Install with: pip install flask", 93)
        return False
    except Exception as e:
        print_colored(f"Failed to start mock server: {e}", 91)
        return False


def _handle_stop(args) -> bool:
    """处理 stop 子命令 / Handle stop subcommand"""
    if args.name not in _mock_servers:
        print_colored(f"Mock server '{args.name}' is not running", 91)
        return False

    server = _mock_servers[args.name]
    server.stop()
    del _mock_servers[args.name]

    print_colored(f"Mock server '{args.name}' stopped", 92)
    return True


def _handle_status(args) -> bool:
    """处理 status 子命令 / Handle status subcommand"""
    if args.name not in _mock_servers:
        print_colored(f"Mock server '{args.name}' is not running", 93)
        return True

    server = _mock_servers[args.name]
    status = "running" if server.is_running() else "stopped"
    routes_count = len(server.config.routes)
    history_count = len(server.get_request_history())

    print_colored(f"Mock Server: {args.name}", 96)
    print(f"  Status: {status}")
    print(f"  Port: {server.config.port}")
    print(f"  Host: {server.config.host}")
    print(f"  Routes: {routes_count}")
    print(f"  Request History: {history_count}")
    return True


def _handle_logs(args) -> bool:
    """处理 logs 子命令 / Handle logs subcommand"""
    if args.name not in _mock_servers:
        print_colored(f"Mock server '{args.name}' is not running", 91)
        return False

    server = _mock_servers[args.name]
    history = server.get_request_history()

    if not history:
        print_colored("No request history", 93)
        return True

    print_colored(f"Request History for '{args.name}' (last {args.limit}):", 96)
    for request in history[-args.limit :]:
        print(f"  [{request.method}] {request.path}")
        if request.body:
            print(f"    Body: {json.dumps(request.body, ensure_ascii=False)[:100]}")

    return True


def _handle_list() -> bool:
    """处理 list 子命令 / Handle list subcommand"""
    if not _mock_servers:
        print_colored("No mock servers running", 93)
        return True

    print_colored("Running Mock Servers:", 96)
    for name, server in _mock_servers.items():
        status = "running" if server.is_running() else "stopped"
        print(f"  • {name} ({status}) - port {server.config.port}")

    return True


def _handle_add_route(args) -> bool:
    """处理 add-route 子命令 / Handle add-route subcommand"""
    if args.name not in _mock_servers:
        print_colored(f"Mock server '{args.name}' is not running", 91)
        return False

    try:
        response = json.loads(args.response)
        when = json.loads(args.when) if args.when else None

        server = _mock_servers[args.name]
        route_id = server.add_route(args.path, args.method, response, when)

        print_colored(f"Route added: {args.method} {args.path}", 92)
        print(f"  Route ID: {route_id}")
        return True

    except json.JSONDecodeError as e:
        print_colored(f"Invalid JSON: {e}", 91)
        return False
    except Exception as e:
        print_colored(f"Failed to add route: {e}", 91)
        return False
