#!/usr/bin/env python3
"""Lightweight stateful API service for problem replay validation."""

from __future__ import annotations

import argparse
import json
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class StatefulOrdersState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._failure_armed = False
        self._orders_requests = 0

    def arm_failure(self) -> dict[str, Any]:
        with self._lock:
            self._failure_armed = True
            return {
                "status": "armed",
                "failure_armed": self._failure_armed,
                "orders_requests": self._orders_requests,
            }

    def snapshot(self, *, status: str = "ok") -> dict[str, Any]:
        with self._lock:
            return {
                "status": status,
                "failure_armed": self._failure_armed,
                "orders_requests": self._orders_requests,
            }

    def next_orders_response(self) -> dict[str, Any]:
        with self._lock:
            self._orders_requests += 1
            if self._failure_armed:
                self._failure_armed = False
                return {
                    "status": "degraded",
                    "orders": [],
                    "reason": "hidden dependency triggered",
                    "failure_armed": False,
                }
            return {
                "status": "ok",
                "orders": [
                    {
                        "id": "A100",
                        "state": "ready",
                    }
                ],
                "failure_armed": False,
            }


class StatefulAPIHandler(BaseHTTPRequestHandler):
    state = StatefulOrdersState()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return

    def _write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/state/check":
            self._write_json(HTTPStatus.OK, self.state.snapshot())
            return
        if self.path == "/api/orders":
            self._write_json(HTTPStatus.OK, self.state.next_orders_response())
            return
        self._write_json(
            HTTPStatus.NOT_FOUND,
            {"status": "missing", "path": self.path},
        )

    def do_POST(self) -> None:  # noqa: N802
        content_length = int(self.headers.get("Content-Length", "0") or 0)
        if content_length > 0:
            self.rfile.read(content_length)
        if self.path == "/state/enable-failure":
            self._write_json(HTTPStatus.OK, self.state.arm_failure())
            return
        self._write_json(
            HTTPStatus.NOT_FOUND,
            {"status": "missing", "path": self.path},
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Start the lightweight stateful API replay validation service."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18090)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), StatefulAPIHandler)
    print(
        json.dumps(
            {
                "status": "serving",
                "host": args.host,
                "port": args.port,
                "service": "stateful_api_replay",
            },
            ensure_ascii=False,
        )
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
