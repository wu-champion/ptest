import unittest
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from ptest.assertions import (  # noqa: E402
    Assertion,
    AssertionResult,
    AssertionFactory,
    AssertionRegistry,
    AndAssertion,
    OrAssertion,
    NotAssertion,
    AssertionTemplate,
    ChainBuilder,
)


class TestAssertionResult(unittest.TestCase):
    def test_passed_result(self):
        result = AssertionResult(passed=True, actual=1, expected=1)
        self.assertTrue(result.is_passed())
        self.assertFalse(result.is_failed())

    def test_failed_result(self):
        result = AssertionResult(passed=False, actual=1, expected=2)
        self.assertFalse(result.is_passed())
        self.assertTrue(result.is_failed())

    def test_to_dict(self):
        result = AssertionResult(
            passed=False,
            actual=1,
            expected=2,
            assertion_type="EqualAssertion",
            description="test",
            message="error",
        )
        d = result.to_dict()
        self.assertEqual(d["passed"], False)
        self.assertEqual(d["actual"], 1)
        self.assertEqual(d["expected"], 2)
        self.assertEqual(d["assertion_type"], "EqualAssertion")

    def test_from_dict(self):
        data = {
            "passed": True,
            "actual": "hello",
            "expected": "hello",
            "assertion_type": "EqualAssertion",
        }
        result = AssertionResult.from_dict(data)
        self.assertTrue(result.passed)
        self.assertEqual(result.actual, "hello")

    def test_error_message_format(self):
        result = AssertionResult(
            passed=False,
            actual=1,
            expected=2,
            assertion_type="EqualAssertion",
            description="test equality",
        )
        msg = result.get_error_message()
        self.assertIn("test equality", msg)
        self.assertIn("EqualAssertion", msg)
        self.assertIn("1", msg)
        self.assertIn("2", msg)

    def test_error_message_with_location(self):
        result = AssertionResult(
            passed=False,
            actual=1,
            expected=2,
            assertion_type="EqualAssertion",
            file_path="/test/example.py",
            line_number=10,
            function_name="test_func",
        )
        msg = result.get_error_message()
        self.assertIn("/test/example.py", msg)
        self.assertIn("10", msg)
        self.assertIn("test_func", msg)

    def test_error_message_with_fix_suggestion(self):
        result = AssertionResult(
            passed=False,
            actual=1,
            expected=2,
            assertion_type="EqualAssertion",
            fix_suggestion="检查比较的值是否正确",
        )
        msg = result.get_error_message()
        self.assertIn("检查比较的值是否正确", msg)

    def test_empty_error_message_on_pass(self):
        result = AssertionResult(passed=True, actual=1, expected=1)
        self.assertEqual(result.get_error_message(), "")


class TestAssertionFactory(unittest.TestCase):
    def test_create_equal_assertion(self):
        assertion = AssertionFactory.create("equal")
        self.assertIsInstance(assertion, Assertion)

    def test_create_notequal_assertion(self):
        assertion = AssertionFactory.create("notequal")
        self.assertIsInstance(assertion, Assertion)

    def test_create_contains_assertion(self):
        assertion = AssertionFactory.create("contains")
        self.assertIsInstance(assertion, Assertion)

    def test_create_truthy_assertion(self):
        assertion = AssertionFactory.create("truthy")
        self.assertIsInstance(assertion, Assertion)

    def test_create_falsy_assertion(self):
        assertion = AssertionFactory.create("falsy")
        self.assertIsInstance(assertion, Assertion)

    def test_create_none_assertion(self):
        assertion = AssertionFactory.create("none")
        self.assertIsInstance(assertion, Assertion)

    def test_create_notnone_assertion(self):
        assertion = AssertionFactory.create("notnone")
        self.assertIsInstance(assertion, Assertion)

    def test_create_type_assertion(self):
        assertion = AssertionFactory.create("type")
        self.assertIsInstance(assertion, Assertion)

    def test_create_statuscode_assertion(self):
        assertion = AssertionFactory.create("statuscode")
        self.assertIsInstance(assertion, Assertion)

    def test_create_jsonpath_assertion(self):
        assertion = AssertionFactory.create("jsonpath")
        self.assertIsInstance(assertion, Assertion)

    def test_create_header_assertion(self):
        assertion = AssertionFactory.create("header")
        self.assertIsInstance(assertion, Assertion)

    def test_create_body_assertion(self):
        assertion = AssertionFactory.create("body")
        self.assertIsInstance(assertion, Assertion)

    def test_create_regex_assertion(self):
        assertion = AssertionFactory.create("regex")
        self.assertIsInstance(assertion, Assertion)

    def test_create_schema_assertion(self):
        assertion = AssertionFactory.create("schema")
        self.assertIsInstance(assertion, Assertion)

    def test_create_length_assertion(self):
        assertion = AssertionFactory.create("length")
        self.assertIsInstance(assertion, Assertion)

    def test_invalid_assertion_type(self):
        with self.assertRaises(ValueError):
            AssertionFactory.create("invalid_type")

    def test_list_available(self):
        available = AssertionFactory.list_available()
        self.assertIn("equal", available)
        self.assertIn("statuscode", available)


class TestEqualAssertion(unittest.TestCase):
    def test_equal_passes(self):
        assertion = AssertionFactory.create("equal")
        result = assertion.assert_value(1, 1)
        self.assertTrue(result.passed)

    def test_equal_fails(self):
        assertion = AssertionFactory.create("equal")
        result = assertion.assert_value(1, 2)
        self.assertFalse(result.passed)

    def test_equal_with_description(self):
        assertion = AssertionFactory.create("equal", description="test desc")
        result = assertion.assert_value(1, 2)
        self.assertFalse(result.passed)
        self.assertEqual(result.description, "test desc")


class TestNotEqualAssertion(unittest.TestCase):
    def test_not_equal_passes(self):
        assertion = AssertionFactory.create("notequal")
        result = assertion.assert_value(1, 2)
        self.assertTrue(result.passed)

    def test_not_equal_fails(self):
        assertion = AssertionFactory.create("notequal")
        result = assertion.assert_value(1, 1)
        self.assertFalse(result.passed)


class TestContainsAssertion(unittest.TestCase):
    def test_contains_passes(self):
        assertion = AssertionFactory.create("contains")
        result = assertion.assert_value("hello world", "world")
        self.assertTrue(result.passed)

    def test_contains_fails(self):
        assertion = AssertionFactory.create("contains")
        result = assertion.assert_value("hello", "xyz")
        self.assertFalse(result.passed)

    def test_contains_list(self):
        assertion = AssertionFactory.create("contains")
        result = assertion.assert_value([1, 2, 3], 2)
        self.assertTrue(result.passed)


class TestTruthyAssertion(unittest.TestCase):
    def test_truthy_string_passes(self):
        assertion = AssertionFactory.create("truthy")
        result = assertion.assert_value("hello")
        self.assertTrue(result.passed)

    def test_truthy_number_passes(self):
        assertion = AssertionFactory.create("truthy")
        result = assertion.assert_value(42)
        self.assertTrue(result.passed)

    def test_truthy_none_fails(self):
        assertion = AssertionFactory.create("truthy")
        result = assertion.assert_value(None)
        self.assertFalse(result.passed)

    def test_truthy_zero_fails(self):
        assertion = AssertionFactory.create("truthy")
        result = assertion.assert_value(0)
        self.assertFalse(result.passed)

    def test_truthy_empty_string_fails(self):
        assertion = AssertionFactory.create("truthy")
        result = assertion.assert_value("")
        self.assertFalse(result.passed)


class TestFalsyAssertion(unittest.TestCase):
    def test_falsy_none_passes(self):
        assertion = AssertionFactory.create("falsy")
        result = assertion.assert_value(None)
        self.assertTrue(result.passed)

    def test_falsy_zero_passes(self):
        assertion = AssertionFactory.create("falsy")
        result = assertion.assert_value(0)
        self.assertTrue(result.passed)

    def test_falsy_empty_string_passes(self):
        assertion = AssertionFactory.create("falsy")
        result = assertion.assert_value("")
        self.assertTrue(result.passed)

    def test_falsy_string_fails(self):
        assertion = AssertionFactory.create("falsy")
        result = assertion.assert_value("hello")
        self.assertFalse(result.passed)


class TestNoneAssertion(unittest.TestCase):
    def test_none_passes(self):
        assertion = AssertionFactory.create("none")
        result = assertion.assert_value(None)
        self.assertTrue(result.passed)

    def test_none_fails(self):
        assertion = AssertionFactory.create("none")
        result = assertion.assert_value("not none")
        self.assertFalse(result.passed)


class TestNotNoneAssertion(unittest.TestCase):
    def test_not_none_passes(self):
        assertion = AssertionFactory.create("notnone")
        result = assertion.assert_value("value")
        self.assertTrue(result.passed)

    def test_not_none_fails(self):
        assertion = AssertionFactory.create("notnone")
        result = assertion.assert_value(None)
        self.assertFalse(result.passed)


class TestTypeAssertion(unittest.TestCase):
    def test_type_string_passes(self):
        assertion = AssertionFactory.create("type")
        result = assertion.assert_value("hello", "str")
        self.assertTrue(result.passed)

    def test_type_int_passes(self):
        assertion = AssertionFactory.create("type")
        result = assertion.assert_value(123, "int")
        self.assertTrue(result.passed)

    def test_type_mismatch_fails(self):
        assertion = AssertionFactory.create("type")
        result = assertion.assert_value("hello", "int")
        self.assertFalse(result.passed)


class TestStatusCodeAssertion(unittest.TestCase):
    def test_status_code_equal_passes(self):
        assertion = AssertionFactory.create("statuscode")
        result = assertion.assert_value(200, 200)
        self.assertTrue(result.passed)

    def test_status_code_not_equal_fails(self):
        assertion = AssertionFactory.create("statuscode")
        result = assertion.assert_value(404, 200)
        self.assertFalse(result.passed)

    def test_status_code_list_passes(self):
        assertion = AssertionFactory.create("statuscode")
        result = assertion.assert_value(404, [200, 201, 404])
        self.assertTrue(result.passed)

    def test_invalid_status_code(self):
        assertion = AssertionFactory.create("statuscode")
        result = assertion.assert_value("not a code", 200)
        self.assertFalse(result.passed)


class TestRegexAssertion(unittest.TestCase):
    def test_regex_match_passes(self):
        assertion = AssertionFactory.create("regex")
        result = assertion.assert_value("hello world", r"world")
        self.assertTrue(result.passed)

    def test_regex_no_match_fails(self):
        assertion = AssertionFactory.create("regex")
        result = assertion.assert_value("hello", r"xyz")
        self.assertFalse(result.passed)

    def test_invalid_regex(self):
        assertion = AssertionFactory.create("regex")
        result = assertion.assert_value("test", r"[invalid")
        self.assertFalse(result.passed)


class TestLengthAssertion(unittest.TestCase):
    def test_length_equal_passes(self):
        assertion = AssertionFactory.create("length")
        result = assertion.assert_value("hello", 5)
        self.assertTrue(result.passed)

    def test_length_greater_passes(self):
        assertion = AssertionFactory.create("length")
        result = assertion.assert_value("hello", 3, operator=">")
        self.assertTrue(result.passed)

    def test_length_less_passes(self):
        assertion = AssertionFactory.create("length")
        result = assertion.assert_value("hi", 5, operator="<")
        self.assertTrue(result.passed)

    def test_length_list(self):
        assertion = AssertionFactory.create("length")
        result = assertion.assert_value([1, 2, 3], 3)
        self.assertTrue(result.passed)


class TestJsonPathAssertion(unittest.TestCase):
    def test_jsonpath_simple_passes(self):
        assertion = AssertionFactory.create("jsonpath")
        data = {"name": "test", "value": 42}
        result = assertion.assert_value(data, "test", path="name")
        self.assertTrue(result.passed)

    def test_jsonpath_nested_passes(self):
        assertion = AssertionFactory.create("jsonpath")
        data = {"user": {"name": "test"}}
        result = assertion.assert_value(data, "test", path="user.name")
        self.assertTrue(result.passed)

    def test_jsonpath_invalid_path(self):
        assertion = AssertionFactory.create("jsonpath")
        data = {"name": "test"}
        result = assertion.assert_value(data, "other", path="notexist")
        self.assertFalse(result.passed)


class TestHeaderAssertion(unittest.TestCase):
    def test_header_exists_passes(self):
        assertion = AssertionFactory.create("header")
        headers = {"content-type": "application/json"}
        result = assertion.assert_value(headers, None, header="content-type")
        self.assertTrue(result.passed)

    def test_header_value_passes(self):
        assertion = AssertionFactory.create("header")
        headers = {"content-type": "application/json"}
        result = assertion.assert_value(
            headers, "application/json", header="content-type"
        )
        self.assertTrue(result.passed)

    def test_header_not_exists_fails(self):
        assertion = AssertionFactory.create("header")
        headers = {"content-type": "application/json"}
        result = assertion.assert_value(headers, None, header="x-custom")
        self.assertFalse(result.passed)


class TestBodyAssertion(unittest.TestCase):
    def test_body_equal_passes(self):
        assertion = AssertionFactory.create("body")
        result = assertion.assert_value({"key": "value"}, {"key": "value"})
        self.assertTrue(result.passed)

    def test_body_json_string_passes(self):
        assertion = AssertionFactory.create("body")
        result = assertion.assert_value('{"key":"value"}', {"key": "value"})
        self.assertTrue(result.passed)


class TestSchemaAssertion(unittest.TestCase):
    def test_schema_type_passes(self):
        assertion = AssertionFactory.create("schema")
        result = assertion.assert_value(
            {"name": "test"}, None, schema={"type": "object"}
        )
        self.assertTrue(result.passed)

    def test_schema_type_string_passes(self):
        assertion = AssertionFactory.create("schema")
        result = assertion.assert_value("hello", None, schema={"type": "string"})
        self.assertTrue(result.passed)

    def test_schema_type_mismatch_fails(self):
        assertion = AssertionFactory.create("schema")
        result = assertion.assert_value(123, None, schema={"type": "string"})
        self.assertFalse(result.passed)


class TestAssertionRegistry(unittest.TestCase):
    def setUp(self):
        AssertionRegistry.clear()

    def test_register_custom_assertion(self):
        class CustomAssertion(Assertion):
            def assert_value(self, actual, expected=None, **kwargs):
                return AssertionResult(
                    passed=actual == expected, actual=actual, expected=expected
                )

        AssertionRegistry.register("custom", CustomAssertion)
        self.assertTrue(AssertionRegistry.is_registered("custom"))
        self.assertIsNotNone(AssertionRegistry.get("custom"))

    def test_unregister(self):
        class CustomAssertion(Assertion):
            def assert_value(self, actual, expected=None, **kwargs):
                return AssertionResult(passed=True)

        AssertionRegistry.register("temp", CustomAssertion)
        self.assertTrue(AssertionRegistry.unregister("temp"))
        self.assertFalse(AssertionRegistry.is_registered("temp"))

    def test_list_types(self):
        class CustomAssertion(Assertion):
            def assert_value(self, actual, expected=None, **kwargs):
                return AssertionResult(passed=True)

        AssertionRegistry.register("test_type", CustomAssertion)
        types = AssertionRegistry.list_types()
        self.assertIn("test_type", types)


if __name__ == "__main__":
    unittest.main()


class TestChainAssertions(unittest.TestCase):
    def test_and_all_pass(self):
        eq = AssertionFactory.create("equal")
        truthy = AssertionFactory.create("truthy")
        and_assert = AndAssertion(eq, truthy)
        result = and_assert.assert_value(42, 42)
        self.assertTrue(result.passed)

    def test_and_one_fails(self):
        eq = AssertionFactory.create("equal")
        truthy = AssertionFactory.create("truthy")
        and_assert = AndAssertion(eq, truthy)
        result = and_assert.assert_value(42, 43)
        self.assertFalse(result.passed)
        self.assertEqual(result.extra.get("failed_count"), 1)

    def test_or_one_passes(self):
        eq = AssertionFactory.create("equal")
        truthy = AssertionFactory.create("truthy")
        or_assert = OrAssertion(eq, truthy)
        result = or_assert.assert_value(42, 43)
        self.assertTrue(result.passed)

    def test_or_all_fail(self):
        eq = AssertionFactory.create("equal")
        falsy = AssertionFactory.create("falsy")
        or_assert = OrAssertion(eq, falsy)
        result = or_assert.assert_value(42, 43)
        self.assertFalse(result.passed)

    def test_not_passes_on_failure(self):
        eq = AssertionFactory.create("equal")
        not_assert = NotAssertion(eq)
        result = not_assert.assert_value(42, 43)
        self.assertTrue(result.passed)

    def test_not_fails_on_pass(self):
        eq = AssertionFactory.create("equal")
        not_assert = NotAssertion(eq)
        result = not_assert.assert_value(42, 42)
        self.assertFalse(result.passed)


class TestAssertionTemplates(unittest.TestCase):
    def setUp(self):
        AssertionTemplate.unregister("test_template")

    def test_register_template(self):
        def test_fn(actual, expected=None, **kwargs):
            return AssertionResult(passed=True, actual=actual, expected=expected)

        AssertionTemplate.register("test_template", test_fn)
        self.assertIn("test_template", AssertionTemplate.list_templates())

    def test_create_from_template(self):
        def test_fn(actual, expected=None, **kwargs):
            return AssertionResult(
                passed=actual == expected, actual=actual, expected=expected
            )

        AssertionTemplate.register("eq_template", test_fn)
        template = AssertionTemplate.create("eq_template")
        result = template.assert_value(1, 1)
        self.assertTrue(result.passed)

    def test_unregister_template(self):
        def test_fn(actual, expected=None, **kwargs):
            return AssertionResult(passed=True)

        AssertionTemplate.register("temp", test_fn)
        self.assertTrue(AssertionTemplate.unregister("temp"))
        self.assertNotIn("temp", AssertionTemplate.list_templates())

    def test_builtin_templates(self):
        templates = AssertionTemplate.list_templates()
        self.assertIn("http_response", templates)
        self.assertIn("api_success", templates)


class TestChainBuilder(unittest.TestCase):
    def test_build_single(self):
        eq = AssertionFactory.create("equal")
        builder = ChainBuilder(eq)
        chain = builder.build()
        result = chain.assert_value(1, 1)
        self.assertTrue(result.passed)

    def test_build_and_chain(self):
        eq = AssertionFactory.create("equal")
        truthy = AssertionFactory.create("truthy")
        builder = ChainBuilder(eq)
        chain = builder.and_(truthy).build()
        result = chain.assert_value(42, 42)
        self.assertTrue(result.passed)

    def test_build_with_not(self):
        eq = AssertionFactory.create("equal")
        builder = ChainBuilder(eq)
        chain = builder.not_().build()
        result = chain.assert_value(1, 2)
        self.assertTrue(result.passed)


class TestNestedChains(unittest.TestCase):
    def test_and_with_or(self):
        eq = AssertionFactory.create("equal")
        truthy = AssertionFactory.create("truthy")
        falsy = AssertionFactory.create("falsy")

        chain = AndAssertion(eq, OrAssertion(truthy, falsy))
        result = chain.assert_value(42, 42)
        self.assertTrue(result.passed)

    def test_or_with_and(self):
        eq = AssertionFactory.create("equal")
        truthy = AssertionFactory.create("truthy")
        falsy = AssertionFactory.create("falsy")

        # Or: (eq AND truthy) OR falsy
        # eq(42,42)=T, truthy(42)=T -> T AND T = T
        # So Or(T, falsy(42)=F) = T
        chain = OrAssertion(AndAssertion(eq, truthy), falsy)
        result = chain.assert_value(42, 42)
        self.assertTrue(result.passed)

    def test_not_with_and(self):
        eq = AssertionFactory.create("equal")
        truthy = AssertionFactory.create("truthy")

        chain = AndAssertion(NotAssertion(eq), truthy)
        result = chain.assert_value(42, 43)
        self.assertTrue(result.passed)


class TestTemplateAdvanced(unittest.TestCase):
    def setUp(self):
        AssertionTemplate.unregister("test_param")

    def test_template_with_params(self):
        def param_template(actual, expected=None, **kwargs):
            threshold = kwargs.get("threshold", 10)
            return AssertionResult(
                passed=actual >= threshold,
                actual=actual,
                expected=threshold,
                assertion_type="ParamTemplate",
            )

        AssertionTemplate.register("test_param", param_template)
        template = AssertionTemplate.create("test_param", {"threshold": 50})

        result = template.assert_value(100)
        self.assertTrue(result.passed)

        result = template.assert_value(5)
        self.assertFalse(result.passed)

    def test_template_override_params(self):
        def param_template(actual, expected=None, **kwargs):
            threshold = kwargs.get("threshold", 10)
            return AssertionResult(
                passed=actual >= threshold,
                actual=actual,
                expected=threshold,
                assertion_type="ParamTemplate",
            )

        AssertionTemplate.register("override_test", param_template)
        template = AssertionTemplate.create("override_test", {"threshold": 50})

        result = template.assert_value(30, threshold=20)
        self.assertTrue(result.passed)

    def test_template_invalid_name_raises(self):
        with self.assertRaises(ValueError):
            AssertionTemplate.create("nonexistent_template")

    def test_template_with_description(self):
        def desc_template(actual, expected=None, **kwargs):
            return AssertionResult(
                passed=True,
                actual=actual,
                expected=expected,
                assertion_type="DescTemplate",
            )

        AssertionTemplate.register("desc_test", desc_template)
        template = AssertionTemplate.create(
            "desc_test", description="My custom assertion"
        )
        self.assertEqual(template.description, "My custom assertion")


class TestChainEdgeCases(unittest.TestCase):
    def test_and_single_assertion(self):
        eq = AssertionFactory.create("equal")
        and_chain = AndAssertion(eq)
        result = and_chain.assert_value(1, 1)
        self.assertTrue(result.passed)

    def test_or_single_assertion(self):
        eq = AssertionFactory.create("equal")
        or_chain = OrAssertion(eq)
        result = or_chain.assert_value(1, 1)
        self.assertTrue(result.passed)

    def test_not_none_assertion(self):
        none_assert = AssertionFactory.create("none")
        not_none = NotAssertion(none_assert)
        result = not_none.assert_value("value")
        self.assertTrue(result.passed)

    def test_chain_with_extra_kwargs(self):
        length = AssertionFactory.create("length")
        chain = AndAssertion(length)

        result = chain.assert_value("hello", 5, operator="==")
        self.assertTrue(result.passed)

    def test_or_with_both_passing(self):
        eq = AssertionFactory.create("equal")
        truthy = AssertionFactory.create("truthy")

        or_chain = OrAssertion(eq, truthy)
        result = or_chain.assert_value(42, 42)
        self.assertTrue(result.passed)
