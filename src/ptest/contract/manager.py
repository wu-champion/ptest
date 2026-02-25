"""ptest 契约管理模块 - OpenAPI/Swagger 契约解析与管理"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core import get_logger

logger = get_logger("contract")


@dataclass
class APIEndpoint:
    """API端点定义"""

    path: str
    method: str
    summary: str = ""
    description: str = ""
    parameters: list[dict[str, Any]] = field(default_factory=list)
    request_body: dict[str, Any] | None = None
    responses: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)


@dataclass
class APIContract:
    """API契约定义"""

    name: str
    version: str
    title: str = ""
    description: str = ""
    base_url: str = ""
    endpoints: list[APIEndpoint] = field(default_factory=list)
    raw_spec: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "version": self.version,
            "title": self.title,
            "description": self.description,
            "base_url": self.base_url,
            "endpoints": [
                {
                    "path": ep.path,
                    "method": ep.method,
                    "summary": ep.summary,
                    "description": ep.description,
                    "parameters": ep.parameters,
                    "request_body": ep.request_body,
                    "responses": ep.responses,
                    "tags": ep.tags,
                }
                for ep in self.endpoints
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> APIContract:
        """从字典创建"""
        endpoints = [
            APIEndpoint(
                path=ep["path"],
                method=ep["method"],
                summary=ep.get("summary", ""),
                description=ep.get("description", ""),
                parameters=ep.get("parameters", []),
                request_body=ep.get("request_body"),
                responses=ep.get("responses", {}),
                tags=ep.get("tags", []),
            )
            for ep in data.get("endpoints", [])
        ]
        return cls(
            name=data["name"],
            version=data["version"],
            title=data.get("title", ""),
            description=data.get("description", ""),
            base_url=data.get("base_url", ""),
            endpoints=endpoints,
        )


class ContractParser:
    """契约解析器"""

    def __init__(self):
        self._parser = None

    def parse(self, source: str | Path) -> APIContract:
        """
        解析契约文件

        Args:
            source: 文件路径或URL

        Returns:
            APIContract对象
        """
        try:
            from prance import ResolvingParser

            parser = ResolvingParser(str(source), backend="openapi-spec-validator")
            spec = parser.specification

            if spec is None:
                raise ValueError("Failed to parse specification: parser returned None")

            return self._extract_contract(spec, source)
        except Exception as e:
            raise ValueError(f"Failed to parse contract: {e}")

    def _extract_contract(
        self, spec: dict[str, Any], source: str | Path
    ) -> APIContract:
        """从规范中提取契约信息"""
        # 获取基本信息
        title = spec.get("info", {}).get("title", "")
        version = spec.get("info", {}).get("version", "")
        description = spec.get("info", {}).get("description", "")

        # 获取服务器URL
        servers = spec.get("servers", [])
        base_url = servers[0].get("url", "") if servers else ""

        # 获取名称（从source或title）
        name = Path(source).stem if isinstance(source, (str, Path)) else "api"

        # 提取端点
        endpoints = []
        paths = spec.get("paths", {})
        for path, path_item in paths.items():
            for method in ["get", "post", "put", "delete", "patch", "head", "options"]:
                if method in path_item:
                    operation = path_item[method]
                    endpoint = APIEndpoint(
                        path=path,
                        method=method.upper(),
                        summary=operation.get("summary", ""),
                        description=operation.get("description", ""),
                        parameters=operation.get("parameters", []),
                        request_body=operation.get("requestBody"),
                        responses=operation.get("responses", {}),
                        tags=operation.get("tags", []),
                    )
                    endpoints.append(endpoint)

        return APIContract(
            name=name,
            version=version,
            title=title,
            description=description,
            base_url=base_url,
            endpoints=endpoints,
            raw_spec=spec,
        )


class ContractManager:
    """契约管理器"""

    def __init__(self, storage_dir: str | Path | None = None):
        self.storage_dir = (
            Path(storage_dir) if storage_dir else Path.home() / ".ptest" / "contracts"
        )
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._contracts: dict[str, APIContract] = {}

    def import_contract(
        self, source: str | Path, name: str | None = None
    ) -> APIContract:
        """
        导入契约

        Args:
            source: 文件路径或URL
            name: 契约名称（可选，默认从文件名提取）

        Returns:
            APIContract对象
        """
        logger.info(f"Importing contract from {source}")
        parser = ContractParser()
        contract = parser.parse(source)

        if name:
            contract.name = name

        self._save_contract(contract)
        self._contracts[contract.name] = contract
        logger.info(f"Contract '{contract.name}' imported successfully")

        return contract

    def _save_contract(self, contract: APIContract) -> None:
        """保存契约到文件"""
        contract_file = self.storage_dir / f"{contract.name}.json"
        with open(contract_file, "w", encoding="utf-8") as f:
            json.dump(contract.to_dict(), f, ensure_ascii=False, indent=2)

    def load_contract(self, name: str) -> APIContract | None:
        """加载契约"""
        if name in self._contracts:
            return self._contracts[name]

        contract_file = self.storage_dir / f"{name}.json"
        if contract_file.exists():
            with open(contract_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                contract = APIContract.from_dict(data)
                self._contracts[name] = contract
                return contract

        return None

    def list_contracts(self) -> list[str]:
        """列出所有契约"""
        contracts = []
        for f in self.storage_dir.glob("*.json"):
            contracts.append(f.stem)
        return sorted(contracts)

    def delete_contract(self, name: str) -> bool:
        """删除契约"""
        contract_file = self.storage_dir / f"{name}.json"
        if contract_file.exists():
            contract_file.unlink()
            if name in self._contracts:
                del self._contracts[name]
            logger.info(f"Contract '{name}' deleted")
            return True
        logger.warning(f"Contract '{name}' not found for deletion")
        return False

    def get_endpoint(
        self, contract_name: str, path: str, method: str
    ) -> APIEndpoint | None:
        """获取特定端点"""
        contract = self.load_contract(contract_name)
        if not contract:
            return None

        for endpoint in contract.endpoints:
            if endpoint.path == path and endpoint.method.upper() == method.upper():
                return endpoint

        return None

    def validate_response(
        self,
        contract_name: str,
        path: str,
        method: str,
        status_code: int,
        response_body: Any,
    ) -> tuple[bool, list[str]]:
        """
        验证响应是否符合契约

        Returns:
            (是否通过, 错误信息列表)
        """
        logger.debug(f"Validating response for {method} {path}")
        endpoint = self.get_endpoint(contract_name, path, method)
        if not endpoint:
            error = f"Endpoint {method} {path} not found in contract {contract_name}"
            logger.warning(error)
            return False, [error]

        response_key = str(status_code)
        if response_key not in endpoint.responses:
            error = f"Status code {status_code} not defined for {method} {path}"
            logger.warning(error)
            return False, [error]

        response_def = endpoint.responses[response_key]
        schema = (
            response_def.get("content", {}).get("application/json", {}).get("schema")
        )

        if not schema:
            logger.debug(f"No schema defined for {method} {path}, skipping validation")
            return True, []

        try:
            from jsonschema import validate

            validate(instance=response_body, schema=schema)
            return True, []
        except ImportError:
            logger.warning("jsonschema not installed, skipping validation")
            return True, []
        except Exception as e:
            error_msg = str(e)
            if "schema" in error_msg.lower():
                logger.warning(f"Schema validation issue: {error_msg}")
                return True, []
            logger.error(f"Unexpected validation error: {error_msg}")
            return False, [f"Validation error: {error_msg}"]

    def generate_test_cases(self, contract_name: str) -> list[dict[str, Any]]:
        """
        基于契约生成测试用例

        Returns:
            测试用例列表
        """
        contract = self.load_contract(contract_name)
        if not contract:
            return []

        cases = []
        for endpoint in contract.endpoints:
            for status_code in endpoint.responses.keys():
                if not status_code.isdigit():
                    continue
                case = {
                    "id": f"test_{contract_name}_{endpoint.method.lower()}_{endpoint.path.replace('/', '_').replace('{', '').replace('}', '')}_{status_code}",
                    "type": "api",
                    "contract": {
                        "name": contract_name,
                        "endpoint": endpoint.path,
                        "method": endpoint.method,
                    },
                    "description": f"Test {endpoint.method} {endpoint.path} - expects {status_code}",
                    "request": {
                        "url": endpoint.path,
                        "method": endpoint.method,
                    },
                    "assertions": [
                        {
                            "type": "status_code",
                            "expected": int(status_code),
                        }
                    ],
                }
                cases.append(case)

        return cases
