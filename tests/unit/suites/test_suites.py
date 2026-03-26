# -*- coding: utf-8 -*-
"""测试套件模块单元测试 - ptest 断言版本

迁移说明:
- 原文件使用 pytest/unittest 断言，现已迁移到 ptest 断言
- 迁移对照表:
  - assert x == y → assert_that(x).equals(y)
  - assert x is True → assert_that(x).is_true()
  - assert x is False → assert_that(x).is_false()
  - assert x in y → assert_that(y).contains(x)
  - assert len(x) == n → assert_that(len(x)).equals(n)
  - pytest.raises(E) → assert_raises(E)
"""

import json
import tempfile
from pathlib import Path


from ptest.assertions import assert_that, assert_raises

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

        assert_that(case_ref.case_id).equals("test_case_1")
        assert_that(case_ref.order).equals(1)
        assert_that(case_ref.depends_on).equals(["setup_case"])
        assert_that(case_ref.skip).is_false()

    def test_case_ref_default_values(self):
        """测试CaseRef默认值"""
        case_ref = CaseRef(case_id="test_case", order=1)

        assert_that(case_ref.depends_on).equals([])
        assert_that(case_ref.skip).is_false()
        assert_that(case_ref.skip_reason).is_none()

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
        assert_that(data["case_id"]).equals("test_case")
        assert_that(data["order"]).equals(2)
        assert_that(data["depends_on"]).equals(["dep1"])
        assert_that(data["skip"]).is_true()
        assert_that(data["skip_reason"]).equals("Not ready")

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
        assert_that(case_ref.case_id).equals("test_case")
        assert_that(case_ref.order).equals(3)
        assert_that(case_ref.depends_on).equals(["dep1", "dep2"])


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

        assert_that(suite.name).equals("integration_suite")
        assert_that(suite.description).equals("Integration test suite")
        assert_that(len(suite.setup)).equals(1)
        assert_that(len(suite.cases)).equals(1)
        assert_that(suite.execution_mode).equals(ExecutionMode.SEQUENTIAL)

    def test_suite_default_values(self):
        """测试TestSuite默认值"""
        suite = TestSuite(name="simple_suite")

        assert_that(suite.setup).equals([])
        assert_that(suite.cases).equals([])
        assert_that(suite.teardown).equals([])
        assert_that(suite.execution_mode).equals(ExecutionMode.SEQUENTIAL)
        assert_that(suite.max_workers).equals(4)

    def test_suite_to_dict(self):
        """测试TestSuite序列化"""
        suite = TestSuite(
            name="test_suite",
            cases=[CaseRef(case_id="case_1", order=1)],
            execution_mode=ExecutionMode.PARALLEL,
        )

        data = suite.to_dict()
        assert_that(data["name"]).equals("test_suite")
        assert_that(data["execution_mode"]).equals("parallel")
        assert_that(len(data["cases"])).equals(1)
        assert_that(data["max_workers"]).equals(4)

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
        assert_that(suite.name).equals("test_suite")
        assert_that(suite.description).equals("Test suite")
        assert_that(len(suite.cases)).equals(1)
        assert_that(suite.max_workers).equals(2)

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
        assert_that(is_valid).is_true()
        assert_that(errors).equals([])

    def test_suite_validate_empty_name(self):
        """测试套件验证 - 空名称"""
        suite = TestSuite(name="", cases=[CaseRef(case_id="case_1", order=1)])

        is_valid, errors = suite.validate()
        assert_that(is_valid).is_false()
        has_error = any("名称不能为空" in error for error in errors)
        assert_that(has_error).is_true()

    def test_suite_validate_no_cases(self):
        """测试套件验证 - 无用例"""
        suite = TestSuite(name="empty_suite")

        is_valid, errors = suite.validate()
        assert_that(is_valid).is_false()
        has_error = any("至少需要一个用例" in error for error in errors)
        assert_that(has_error).is_true()

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
        assert_that(is_valid).is_false()
        has_error = any("顺序重复" in error for error in errors)
        assert_that(has_error).is_true()

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
        assert_that(is_valid).is_false()
        has_error = any("依赖不存在" in error for error in errors)
        assert_that(has_error).is_true()

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
        assert_that(sorted_cases[0].case_id).equals("case_1")
        assert_that(sorted_cases[1].case_id).equals("case_2")
        assert_that(sorted_cases[2].case_id).equals("case_3")


class TestSuiteManager:
    """SuiteManager测试类"""

    def test_suite_manager_creation(self):
        """测试SuiteManager创建"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SuiteManager(storage_dir=tmpdir)
            assert_that(manager.storage_dir).equals(Path(tmpdir))

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
            assert_that(suite.name).equals("test_suite")
            assert_that(len(suite.cases)).equals(1)

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

            assert_that(suite.name).equals("file_suite")

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
            assert_that(loaded_suite).not_none()
            assert_that(loaded_suite.name).equals("load_test")

    def test_load_nonexistent_suite(self):
        """测试加载不存在的套件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SuiteManager(storage_dir=tmpdir)
            suite = manager.load_suite("nonexistent")
            assert_that(suite).is_none()

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
            assert_that("suite_a" in suites).is_true()
            assert_that("suite_b" in suites).is_true()

    def test_delete_suite(self):
        """测试删除套件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SuiteManager(storage_dir=tmpdir)

            manager.create_suite(
                {"name": "to_delete", "cases": [{"case_id": "c1", "order": 1}]}
            )
            assert_that(manager.delete_suite("to_delete")).is_true()

            # 验证已删除
            assert_that(manager.load_suite("to_delete")).is_none()

    def test_delete_nonexistent_suite(self):
        """测试删除不存在的套件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SuiteManager(storage_dir=tmpdir)
            assert_that(manager.delete_suite("nonexistent")).is_false()

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
            assert_that(len(cases)).equals(2)
            assert_that(cases[0].case_id).equals("case_1")  # 已排序
            assert_that(cases[1].case_id).equals("case_2")

    def test_create_suite_file_not_found(self):
        """测试创建套件 - 文件不存在"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SuiteManager(storage_dir=tmpdir)

            with assert_raises(FileNotFoundError):
                manager.create_suite(Path(tmpdir) / "nonexistent.json")


class TestExecutionMode:
    """ExecutionMode测试类"""

    def test_execution_mode_values(self):
        """测试执行模式值"""
        assert_that(ExecutionMode.SEQUENTIAL.value).equals("sequential")
        assert_that(ExecutionMode.PARALLEL.value).equals("parallel")

    def test_execution_mode_comparison(self):
        """测试执行模式比较"""
        suite = TestSuite(name="test", execution_mode=ExecutionMode.PARALLEL)
        assert_that(suite.execution_mode).equals(ExecutionMode.PARALLEL)
