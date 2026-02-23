# ptest/cases/manager.py
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
from .result import TestCaseResult
from .executor import TestExecutor

try:
    from ..utils import get_colored_text
except ImportError:

    def get_colored_text(text: Any, color_code: Any) -> str:
        return str(text)

# 尝试导入 YAML
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False



    @staticmethod
    def _is_ci_environment() -> bool:
        """检测是否在 CI 环境中运行"""
        import os
        ci_indicators = [
            "CI",
            "GITHUB_ACTIONS",
            "GITLAB_CI",
            "JENKINS",
            "CIRCLECI",
            "TRAVIS",
            "BITBUCKET",
            "BUILDKITE",
        ]
        return any(os.environ.get(indicator) for indicator in ci_indicators)

class CaseManager:
    """测试用例管理器"""

    def __init__(self, env_manager, auto_save: bool = True, format: str = "yaml"):
        self.env_manager = env_manager
        self.cases: dict[str, Any] = {}
        self.results: dict[str, TestCaseResult] = {}
        self.failed_cases: list[str] = []
        self.passed_cases: list[str] = []
        self.executor = TestExecutor(env_manager)
        self.auto_save = auto_save
        self.format = format  # yaml / json
        self._storage_dir = self._get_storage_dir()
        self._storage_file_yaml = self._storage_dir / "cases.yaml"
        self._storage_file_json = self._storage_dir / "cases.json"

        if self.auto_save:
            self._load_cases()

    def _get_storage_dir(self) -> Path:
        """获取用例存储目录"""
        if self.env_manager.test_path:
            storage_dir = Path(self.env_manager.test_path) / ".ptest"
        else:
            storage_dir = Path.home() / ".ptest"
        storage_dir.mkdir(parents=True, exist_ok=True)
        return storage_dir

    def _get_storage_path(self) -> Path:
        """获取用例存储路径"""
        if self.env_manager.test_path:
            storage_dir = Path(self.env_manager.test_path) / ".ptest"
        else:
            storage_dir = Path.home() / ".ptest"
        storage_dir.mkdir(parents=True, exist_ok=True)
        return storage_dir / "cases.json"

    def _load_cases(self) -> None:
        """从文件加载用例 - 自动检测格式"""
        # 优先加载 YAML
        if self._storage_file_yaml.exists():
            self._load_cases_yaml()
        elif self._storage_file_json.exists():
            self._load_cases_json()

    def _load_cases_yaml(self) -> None:
        """从 YAML 文件加载用例"""
        if not YAML_AVAILABLE:
            self.env_manager.logger.warning(
                "PyYAML not available, falling back to JSON. "
                "Install with: pip install pyyaml"
            )
            self._load_cases_json()
            return
        try:
            with open(self._storage_file_yaml, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data:
                    self.cases = data.get("cases", {})
                    self.failed_cases = data.get("failed_cases", [])
                    self.passed_cases = data.get("passed_cases", [])
        except yaml.YAMLError as e:
            self.env_manager.logger.error(
                f"YAML 格式错误，请检查文件语法: {self._storage_file_yaml}\n"
                f"错误详情: {e}\n"
                "提示: 确保使用正确的 YAML 缩进（2个空格），不要使用 Tab"
            )
            self.cases = {}
        except Exception as e:
            self.env_manager.logger.warning(
                f"加载 YAML 文件失败: {e}, 尝试加载 JSON 格式"
            )
            self._load_cases_json()

    def _load_cases_json(self) -> None:
        """从 JSON 文件加载用例"""
        if self._storage_file_json.exists():
            try:
                with open(self._storage_file_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.cases = data.get("cases", {})
                    self.failed_cases = data.get("failed_cases", [])
                    self.passed_cases = data.get("passed_cases", [])
            except Exception as e:
                self.env_manager.logger.warning(f"Failed to load JSON cases: {e}")
                self.cases = {}

    def _save_cases(self) -> None:
        """保存用例到文件"""
        if not self.auto_save:
            return
        if self.format == "yaml":
            self._save_cases_yaml()
        else:
            self._save_cases_json()

    def _save_cases_yaml(self) -> None:
        """保存用例为 YAML 格式"""
        if not YAML_AVAILABLE:
            self.env_manager.logger.warning("PyYAML not available, saving as JSON instead")
            self._save_cases_json()
            return
        try:
            data = {
                "cases": self.cases,
                "failed_cases": self.failed_cases,
                "passed_cases": self.passed_cases,
                "saved_at": datetime.now().isoformat(),
            }
            with open(self._storage_file_yaml, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
        except Exception as e:
            self.env_manager.logger.warning(f"Failed to save YAML cases: {e}")


    @staticmethod
    def convert_yaml_to_json(yaml_path: str | Path, json_path: str | Path | None = None) -> str:
        """
        将 YAML 文件转换为 JSON 文件

        Args:
            yaml_path: YAML 文件路径
            json_path: 可选的输出 JSON 路径，默认同目录下同名 .json 文件

        Returns:
            转换后的 JSON 文件路径

        Raises:
            FileNotFoundError: YAML 文件不存在
            ValueError: YAML 格式错误
        """
        if not YAML_AVAILABLE:
            raise ImportError("PyYAML is required for YAML conversion. Install it with: pip install pyyaml")

        yaml_path = Path(yaml_path)
        if not yaml_path.exists():
            raise FileNotFoundError(f"YAML file not found: {yaml_path}")

        # 确定输出路径
        if json_path is None:
            json_path = yaml_path.with_suffix(".json")
        else:
            json_path = Path(json_path)

        # 读取 YAML
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # 写入 JSON
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return str(json_path)

    @staticmethod
    def convert_json_to_yaml(json_path: str | Path, yaml_path: str | Path | None = None) -> str:
        """
        将 JSON 文件转换为 YAML 文件

        Args:
            json_path: JSON 文件路径
            yaml_path: 可选的输出 YAML 路径，默认同目录下同名 .yaml 文件

        Returns:
            转换后的 YAML 文件路径

        Raises:
            FileNotFoundError: JSON 文件不存在
        """
        if not YAML_AVAILABLE:
            raise ImportError("PyYAML is required for YAML conversion. Install it with: pip install pyyaml")

        json_path = Path(json_path)
        if not json_path.exists():
            raise FileNotFoundError(f"JSON file not found: {json_path}")

        # 确定输出路径
        if yaml_path is None:
            yaml_path = json_path.with_suffix(".yaml")
        else:
            yaml_path = Path(yaml_path)

        # 读取 JSON
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 写入 YAML
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)

        return str(yaml_path)

    def _save_cases_json(self) -> None:
        """保存用例为 JSON 格式"""
        try:
            data = {
                "cases": self.cases,
                "failed_cases": self.failed_cases,
                "passed_cases": self.passed_cases,
                "saved_at": datetime.now().isoformat(),
            }
            with open(self._storage_file_json, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.env_manager.logger.warning(f"Failed to save JSON cases: {e}")

    def add_case(self, case_id: str, case_data: dict):
        self.cases[case_id] = {
            "id": case_id,
            "data": case_data,
            "created_at": datetime.now().isoformat(),
            "last_run": None,
            "status": "pending",
        }
        self._save_cases()
        self.env_manager.logger.info(f"Test case '{case_id}' added")
        return f"✓ Test case '{case_id}' added"

    def remove_case(self, case_id: str):
        if case_id in self.cases:
            del self.cases[case_id]
            if case_id in self.results:
                del self.results[case_id]
            if case_id in self.passed_cases:
                self.passed_cases.remove(case_id)
            if case_id in self.failed_cases:
                self.failed_cases.remove(case_id)
            self._save_cases()
            self.env_manager.logger.info(f"Test case '{case_id}' removed")
            return f"✓ Test case '{case_id}' removed"
        return f"✗ Test case '{case_id}' does not exist"


    def _merge_params(
        self, case_data: dict[str, Any], params: dict[str, Any]
    ) -> dict[str, Any]:
        """
        合并参数到用例数据中

        Args:
            case_data: 原始用例数据
            params: 需要合并的参数

        Returns:
            合并后的用例数据
        """
        import copy

        merged = copy.deepcopy(case_data)

        # 递归合并参数
        def _deep_merge(base: dict, overlay: dict) -> dict:
            result = copy.deepcopy(base)
            for key, value in overlay.items():
                if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = _deep_merge(result[key], value)
                else:
                    result[key] = copy.deepcopy(value)
            return result

        return _deep_merge(merged, params)

    def get_case(self, case_id: str):
        """获取用例（兼容别名）"""
        return self.cases.get(case_id)

    def delete_case(self, case_id: str) -> bool:
        """删除用例（兼容别名）"""
        result = self.remove_case(case_id)
        return "✓" in result

    def list_cases(self):
        """列出所有测试用例"""
        if not self.cases:
            return "No test cases found"

        result = f"{get_colored_text('Test Cases:', 95)}\n"
        for case_id, case_info in self.cases.items():
            status = case_info["status"].upper()
            color = 92 if status == "PASSED" else 91 if status == "FAILED" else 97
            result += f"{get_colored_text(case_id, 94)} [{get_colored_text(status, color)}] - Created: {case_info['created_at']}\n"
        return result.rstrip()

    def run_case(
        self, case_id: str, params: dict[str, Any] | None = None
    ) -> TestCaseResult:
        """
        运行指定测试用例
        使用真实的测试执行器执行测试

        Args:
            case_id: 用例 ID
            params: 可选的参数字典，会合并到用例数据中

        Returns:
            TestCaseResult: 结构化的测试结果对象
        """
        if case_id not in self.cases:
            result_obj = TestCaseResult(case_id=case_id)
            result_obj.status = "error"
            result_obj.error_message = f"Test case '{case_id}' does not exist"
            result_obj.end_time = datetime.now()
            return result_obj

        case_data = self.cases[case_id]["data"]

        # 合并 params 到 case_data（如果提供）
        if params:
            case_data = self._merge_params(case_data, params)

        self.env_manager.logger.info(f"Running test case: {case_id}")

        # 使用测试执行器执行测试
        result_obj = self.executor.execute_case(case_id, case_data)
        self.results[case_id] = result_obj

        # 更新用例状态和结果列表
        self.cases[case_id]["status"] = result_obj.status
        self.cases[case_id]["last_run"] = result_obj.end_time.isoformat()

        # 更新通过/失败列表
        if result_obj.status == "passed":
            if case_id not in self.passed_cases:
                self.passed_cases.append(case_id)
            if case_id in self.failed_cases:
                self.failed_cases.remove(case_id)
            self.env_manager.logger.info(f"Test case '{case_id}' PASSED")
        elif result_obj.status == "failed":
            if case_id not in self.failed_cases:
                self.failed_cases.append(case_id)
            if case_id in self.passed_cases:
                self.passed_cases.remove(case_id)
            self.env_manager.logger.error(
                f"Test case '{case_id}' FAILED: {result_obj.error_message}"
            )
        else:
            if case_id not in self.failed_cases:
                self.failed_cases.append(case_id)
            if case_id in self.passed_cases:
                self.passed_cases.remove(case_id)
            self.env_manager.logger.error(
                f"Test case '{case_id}' ERROR: {result_obj.error_message}"
            )

        self._save_cases()
        return result_obj

    def run_all_cases(
        self,
        parallel: bool = False,
        show_progress: bool = True,
    ) -> Dict[str, Any]:
        """运行所有测试用例

        Args:
            parallel: 是否并行执行
            show_progress: 是否显示进度条

        Returns:
            Dict[str, Any]: 包含测试结果摘要和详细结果列表
        """
        # 检测是否为 CI 环境
        is_ci = self._is_ci_environment()
        if is_ci:
            show_progress = False

        if not self.cases:
            return {
                "success": False,
                "message": "No test cases to run",
                "total": 0,
                "passed": 0,
                "failed": 0,
                "results": [],
            }

        case_ids = list(self.cases.keys())
        total = len(case_ids)

        self.env_manager.logger.info(f"Running all {total} test cases")
        results = []
        passed_count = 0
        failed_count = 0

        # 尝试导入 tqdm
        try:
            from tqdm import tqdm
            has_tqdm = True
        except ImportError:
            has_tqdm = False

        # 根据配置决定是否显示进度条
        if show_progress and has_tqdm and not is_ci:
            with tqdm(total=total, desc="执行测试用例", unit="用例") as pbar:
                for case_id in case_ids:
                    pbar.set_description(f"执行: {case_id}")
                    result = self.run_case(case_id)
                    results.append(result)
                    if result.status == "passed":
                        passed_count += 1
                        pbar.write(f"✓ {case_id} PASSED")
                    else:
                        failed_count += 1
                        pbar.write(f"✗ {case_id} FAILED")
                    pbar.update(1)
        else:
            # 不显示进度条
            for i, case_id in enumerate(case_ids, 1):
                self.env_manager.logger.info(f"[{i}/{total}] Running: {case_id}")
                result = self.run_case(case_id)
                results.append(result)
                if result.status == "passed":
                    passed_count += 1
                else:
                    failed_count += 1

        return {
            "success": failed_count == 0,
            "message": f"Completed {len(results)} test cases",
            "total": len(results),
            "passed": passed_count,
            "failed": failed_count,
            "results": results,
        }

    def run_failed_cases(self):
        """运行失败的测试用例"""
        if not self.failed_cases:
            return "No failed test cases to run"

        self.env_manager.logger.info(
            f"Running {len(self.failed_cases)} failed test cases"
        )
        results = []
        for case_id in self.failed_cases:
            results.append(self.run_case(case_id))
        return "\n".join(results)
