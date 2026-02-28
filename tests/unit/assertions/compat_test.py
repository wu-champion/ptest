# ptest/assertions/compat_test.py
# pytest/unittest 兼容层测试
#
# 使用 ptest 断言系统测试兼容层功能

import unittest
from ptest.assertions import (
    assert_that,
    assert_raises,
    SoftAssertions,
)


class TestAssertThat(unittest.TestCase):
    """assert_that 测试"""

    def test_equals_pass(self):
        """测试相等断言 - 通过"""
        assert_that(1).equals(1)
        assert_that("hello").equals("hello")

    def test_equals_fail(self):
        """测试相等断言 - 失败"""
        with self.assertRaises(AssertionError):
            assert_that(1).equals(2)

    def test_not_equals_pass(self):
        """测试不相等断言 - 通过"""
        assert_that(1).not_equals(2)

    def test_not_equals_fail(self):
        """测试不相等断言 - 失败"""
        with self.assertRaises(AssertionError):
            assert_that(1).not_equals(1)

    def test_contains_pass(self):
        """测试包含断言 - 通过"""
        assert_that("hello world").contains("world")
        assert_that([1, 2, 3]).contains(2)

    def test_contains_fail(self):
        """测试包含断言 - 失败"""
        with self.assertRaises(AssertionError):
            assert_that("hello").contains("world")

    def test_is_truthy_pass(self):
        """测试真值断言 - 通过"""
        assert_that(True).is_truthy()
        assert_that(1).is_truthy()
        assert_that("hello").is_truthy()

    def test_is_truthy_fail(self):
        """测试真值断言 - 失败"""
        with self.assertRaises(AssertionError):
            assert_that(False).is_truthy()
        with self.assertRaises(AssertionError):
            assert_that(0).is_truthy()

    def test_is_falsy_pass(self):
        """测试假值断言 - 通过"""
        assert_that(False).is_falsy()
        assert_that(0).is_falsy()
        assert_that("").is_falsy()

    def test_is_falsy_fail(self):
        """测试假值断言 - 失败"""
        with self.assertRaises(AssertionError):
            assert_that(True).is_falsy()

    def test_is_none_pass(self):
        """测试 None 断言 - 通过"""
        assert_that(None).is_none()

    def test_is_none_fail(self):
        """测试 None 断言 - 失败"""
        with self.assertRaises(AssertionError):
            assert_that("hello").is_none()

    def test_is_not_none_pass(self):
        """测试非 None 断言 - 通过"""
        assert_that("hello").is_not_none()
        assert_that(1).is_not_none()

    def test_is_not_none_fail(self):
        """测试非 None 断言 - 失败"""
        with self.assertRaises(AssertionError):
            assert_that(None).is_not_none()

    def test_has_length_pass(self):
        """测试长度断言 - 通过"""
        assert_that("hello").has_length(5)
        assert_that([1, 2, 3]).has_length(3)

    def test_has_length_fail(self):
        """测试长度断言 - 失败"""
        with self.assertRaises(AssertionError):
            assert_that("hello").has_length(3)

    def test_matches_pass(self):
        """测试正则匹配 - 通过"""
        assert_that("hello world").matches(r"world")

    def test_matches_fail(self):
        """测试正则匹配 - 失败"""
        with self.assertRaises(AssertionError):
            assert_that("hello").matches(r"world")


class TestAssertRaises(unittest.TestCase):
    """assert_raises 测试"""

    def test_raises_correct_exception(self):
        """测试捕获正确异常"""
        with assert_raises(ValueError):
            raise ValueError("test error")

    def test_raises_wrong_exception(self):
        """测试异常类型不匹配"""
        with self.assertRaises(AssertionError) as ctx:
            with assert_raises(ValueError):
                raise TypeError("wrong type")
        self.assertIn("Expected ValueError", str(ctx.exception))

    def test_raises_no_exception(self):
        """测试没有抛出异常"""
        with self.assertRaises(AssertionError) as ctx:
            with assert_raises(ValueError):
                pass  # 没有抛出异常
        self.assertIn("no exception was raised", str(ctx.exception))

    def test_exception_access(self):
        """测试访问捕获的异常"""
        with assert_raises(ValueError) as ctx:
            raise ValueError("test error")
        self.assertEqual(str(ctx.exception), "test error")


class TestSoftAssertions(unittest.TestCase):
    """SoftAssertions 测试"""

    def test_soft_all_pass(self):
        """测试软断言全部通过"""
        with SoftAssertions() as soft:
            soft.assert_that(1).equals(1)
            soft.assert_that("a").equals("a")

    def test_soft_partial_fail(self):
        """测试软断言部分失败"""
        with self.assertRaises(AssertionError) as ctx:
            with SoftAssertions() as soft:
                soft.assert_that(1).equals(1)  # 通过
                soft.assert_that(1).equals(2)  # 失败
                soft.assert_that("a").equals("b")  # 失败

        error_msg = str(ctx.exception)
        self.assertIn("Soft assertion failures (2)", error_msg)

    def test_soft_no_failure(self):
        """测试无失败时不抛异常"""
        with SoftAssertions() as soft:
            soft.assert_that(True).is_truthy()
        # 应该正常退出，不抛异常

    def test_soft_collects_all_failures(self):
        """测试收集所有失败"""
        with self.assertRaises(AssertionError) as ctx:
            with SoftAssertions() as soft:
                soft.assert_that(1).equals(2)
                soft.assert_that(2).equals(3)
                soft.assert_that(3).equals(4)

        error_msg = str(ctx.exception)
        self.assertIn("Soft assertion failures (3)", error_msg)


class TestCompatibility(unittest.TestCase):
    """兼容性测试 - 确保在 pytest/unittest 中正常工作"""

    def test_works_in_unittest(self):
        """确保在 unittest 环境中正常工作"""
        # 这是一个 unittest 测试，应该正常工作
        assert_that(1).equals(1)
        assert_that([1, 2, 3]).has_length(3)

    def test_unittest_assertion_error(self):
        """确保抛出标准的 AssertionError"""
        with self.assertRaises(AssertionError):
            assert_that(1).equals(2)

    def test_chain_assertions(self):
        """测试链式调用"""
        # 可以连续调用
        result = assert_that("hello")
        result.equals("hello")
        result.contains("ell")


if __name__ == "__main__":
    unittest.main()
