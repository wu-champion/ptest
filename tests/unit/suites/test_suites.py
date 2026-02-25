# -*- coding: utf-8 -*-
"""测试套件模块单元测试 / Test Suite Module Unit Tests"""

import json
import tempfile
from pathlib import Path

import pytest

from ptest.suites import CaseRef, ExecutionMode, SuiteManager, TestSuite


class TestCaseRef:
    """CaseRef测试类"""

    def test_case_ref_creation(self):
        """测试CaseRef创建"""
        case_ref = CaseRef(
            case_id="test_case_1",
            order=1,
            depends_on=["setup_case"],
            skip=False,
            skip_reason=None,
        )

        assert case_ref.case_id == "test_case_1"
        assert case_ref.order == 1
        assert case_ref.depends_on == ["setup_case"]
        assert case_ref.skip is False

    def test_case_ref_default_values(self):
        """测试CaseRef默认值"""
        case_ref = CaseRef(case_id="test_case", order=1)

        assert case_ref.depends_on == []
        assert case_ref.skip is False
        assert case_ref.skip_reason is None

    def test_case_ref_to_dict(self):
        """测试CaseRef序列化"""
        case_ref = CaseRef(
            case_id="test_case",
            order=2,
            depends_on=["dep1"],
            skip=True,
            skip_reason="Not ready",
        )

        data = case_ref.to_dict()
        assert data["case_id"] == "test_case"
        assert data["order"] == 2
        assert data["depends_on"] == ["dep1"]
        assert data["skip"] is True
        assert data["skip_reason"] == "Not ready"

    def test_case_ref_from_dict(self):
        """测试CaseRef反序列化"""
        data = {
            "case_id": "test_case",
            "order": 3,
            "depends_on": ["dep1", "dep2"],
            "skip": False,
            "skip_reason": None,
        }

        case_ref = CaseRef.from_dict(data)
        assert case_ref.case_id == "test_case"
        assert case_ref.order == 3
        assert case_ref.depends_on == ["dep1", "dep2"]


class TestTestSuite:
    """TestSuite测试类"""

    def test_suite_creation(self):
        """测试TestSuite创建"""
        suite = TestSuite(
            name="integration_suite",
            description="Integration test suite",
            setup=["setup_db"],
            cases=[CaseRef(case_id="test_1", order=1)],
            teardown=["cleanup"],
            execution_mode=ExecutionMode.SEQUENTIAL,
            max_workers=2,
        )

        assert suite.name == "integration_suite"
        assert suite.description == "Integration test suite"
        assert len(suite.setup) == 1
        assert len(suite.cases) == 1
        assert suite.execution_mode == ExecutionMode.SEQUENTIAL

    def test_suite_default_values(self):
        """测试TestSuite默认值"""
        suite = TestSuite(name="simple_suite")

        assert suite.setup == []
        assert suite.cases == []
        assert suite.teardown == []
        assert suite.execution_mode == ExecutionMode.SEQUENTIAL
        assert suite.max_workers == 4

    def test_suite_to_dict(self):
        """测试TestSuite序列化"""
        suite = TestSuite(
            name="test_suite",
            cases=[CaseRef(case_id="case_1", order=1)],
            execution_mode=ExecutionMode.PARALLEL,
        )

        data = suite.to_dict()
        assert data["name"] == "test_suite"
        assert data["execution_mode"] == "parallel"
        assert len(data["cases"]) == 1
        assert data["max_workers"] == 4

    def test_suite_from_dict(self):
        """测试TestSuite反序列化"""
        data = {
            "name": "test_suite",
            "description": "Test suite",
            "setup": ["setup_step"],
            "cases": [{"case_id": "case_1", "order": 1}],
            "teardown": ["teardown_step"],
            "execution_mode": "sequential",
            "max_workers": 2,
        }

        suite = TestSuite.from_dict(data)
        assert suite.name == "test_suite"
        assert suite.description == "Test suite"
        assert len(suite.cases) == 1
        assert suite.max_workers == 2

    def test_suite_validate_success(self):
        """测试套件验证成功"""
        suite = TestSuite(
            name="valid_suite",
            cases=[
                CaseRef(case_id="case_1", order=1),
                CaseRef(case_id="case_2", order=2),
            ],
        )

        is_valid, errors = suite.validate()
        assert is_valid is True
        assert errors == []

    def test_suite_validate_empty_name(self):
        """测试套件验证 - 空名称"""
        suite = TestSuite(name="", cases=[CaseRef(case_id="case_1", order=1)])

        is_valid, errors = suite.validate()
        assert is_valid is False
        assert any("名称不能为空" in error for error in errors)

    def test_suite_validate_no_cases(self):
        """测试套件验证 - 无用例"""
        suite = TestSuite(name="empty_suite")

        is_valid, errors = suite.validate()
        assert is_valid is False
        assert any("至少需要一个用例" in error for error in errors)

    def test_suite_validate_duplicate_orders(self):
        """测试套件验证 - 重复顺序"""
        suite = TestSuite(
            name="suite",
            cases=[
                CaseRef(case_id="case_1", order=1),
                CaseRef(case_id="case_2", order=1),
            ],
        )

        is_valid, errors = suite.validate()
        assert is_valid is False
        assert any("顺序重复" in error for error in errors)

    def test_suite_validate_missing_dependency(self):
        """测试套件验证 - 依赖不存在"""
        suite = TestSuite(
            name="suite",
            cases=[
                CaseRef(case_id="case_1", order=1),
                CaseRef(case_id="case_2", order=2, depends_on=["non_existent"]),
            ],
        )

        is_valid, errors = suite.validate()
        assert is_valid is False
        assert any("依赖不存在" in error for error in errors)

    def test_get_sorted_cases(self):
        """测试获取排序后的用例"""
        suite = TestSuite(
            name="suite",
            cases=[
                CaseRef(case_id="case_3", order=3),
                CaseRef(case_id="case_1", order=1),
                CaseRef(case_id="case_2", order=2),
            ],
        )

        sorted_cases = suite.get_sorted_cases()
        assert sorted_cases[0].case_id == "case_1"
        assert sorted_cases[1].case_id == "case_2"
        assert sorted_cases[2].case_id == "case_3"


class TestSuiteManager:
    """SuiteManager测试类"""

    def test_suite_manager_creation(self):
        """测试SuiteManager创建"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SuiteManager(storage_dir=tmpdir)
            assert manager.storage_dir == Path(tmpdir)

    def test_create_suite_from_dict(self):
        """测试从字典创建套件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SuiteManager(storage_dir=tmpdir)

            suite_data = {
                "name": "test_suite",
                "description": "Test suite",
                "cases": [{"case_id": "case_1", "order": 1}],
            }

            suite = manager.create_suite(suite_data)
            assert suite.name == "test_suite"
            assert len(suite.cases) == 1

    def test_create_suite_from_file(self):
        """测试从文件创建套件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建测试文件
            suite_file = Path(tmpdir) / "test_suite.json"
            suite_data = {
                "name": "file_suite",
                "cases": [{"case_id": "case_1", "order": 1}],
            }
            suite_file.write_text(json.dumps(suite_data), encoding="utf-8")

            manager = SuiteManager(storage_dir=tmpdir)
            suite = manager.create_suite(suite_file)

            assert suite.name == "file_suite"

    def test_load_suite(self):
        """测试加载套件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SuiteManager(storage_dir=tmpdir)

            # 先创建套件
            suite_data = {
                "name": "load_test",
                "cases": [{"case_id": "case_1", "order": 1}],
            }
            manager.create_suite(suite_data)

            # 再加载
            loaded_suite = manager.load_suite("load_test")
            assert loaded_suite is not None
            assert loaded_suite.name == "load_test"

    def test_load_nonexistent_suite(self):
        """测试加载不存在的套件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SuiteManager(storage_dir=tmpdir)
            suite = manager.load_suite("nonexistent")
            assert suite is None

    def test_list_suites(self):
        """测试列出所有套件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SuiteManager(storage_dir=tmpdir)

            manager.create_suite(
                {"name": "suite_a", "cases": [{"case_id": "c1", "order": 1}]}
            )
            manager.create_suite(
                {"name": "suite_b", "cases": [{"case_id": "c2", "order": 1}]}
            )

            suites = manager.list_suites()
            assert "suite_a" in suites
            assert "suite_b" in suites

    def test_delete_suite(self):
        """测试删除套件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SuiteManager(storage_dir=tmpdir)

            manager.create_suite(
                {"name": "to_delete", "cases": [{"case_id": "c1", "order": 1}]}
            )
            assert manager.delete_suite("to_delete") is True

            # 验证已删除
            assert manager.load_suite("to_delete") is None

    def test_delete_nonexistent_suite(self):
        """测试删除不存在的套件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SuiteManager(storage_dir=tmpdir)
            assert manager.delete_suite("nonexistent") is False

    def test_get_suite_cases(self):
        """测试获取套件用例"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SuiteManager(storage_dir=tmpdir)

            manager.create_suite(
                {
                    "name": "case_test",
                    "cases": [
                        {"case_id": "case_2", "order": 2},
                        {"case_id": "case_1", "order": 1},
                    ],
                }
            )

            cases = manager.get_suite_cases("case_test")
            assert len(cases) == 2
            assert cases[0].case_id == "case_1"  # 已排序
            assert cases[1].case_id == "case_2"

    def test_create_suite_file_not_found(self):
        """测试创建套件 - 文件不存在"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SuiteManager(storage_dir=tmpdir)

            with pytest.raises(FileNotFoundError):
                manager.create_suite(Path(tmpdir) / "nonexistent.json")


class TestExecutionMode:
    """ExecutionMode测试类"""

    def test_execution_mode_values(self):
        """测试执行模式值"""
        assert ExecutionMode.SEQUENTIAL.value == "sequential"
        assert ExecutionMode.PARALLEL.value == "parallel"

    def test_execution_mode_comparison(self):
        """测试执行模式比较"""
        suite = TestSuite(name="test", execution_mode=ExecutionMode.PARALLEL)
        assert suite.execution_mode == ExecutionMode.PARALLEL
