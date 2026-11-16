from pathlib import Path

import pytest

from ci_failure_analyzer.inputs.junit import JUnitParseError, parse_junit, parse_junit_bytes

FIXTURES = Path(__file__).parent / "fixtures"


def test_counts_each_outcome():
    report = parse_junit(FIXTURES / "junit_mixed.xml")
    assert len(report.cases) == 5
    assert report.count("passed") == 1
    assert report.count("failed") == 2
    assert report.count("error") == 1
    assert report.count("skipped") == 1


def test_failed_includes_failures_and_errors_but_not_skips():
    report = parse_junit(FIXTURES / "junit_mixed.xml")
    assert [c.name for c in report.failed] == [
        "test_bulk",
        "test_setup_breaks",
        "test_fail_then_teardown_error",
    ]


def test_failure_message_and_traceback_are_kept():
    case = parse_junit(FIXTURES / "junit_mixed.xml").failed[0]
    assert case.message == "AssertionError: assert 10000 == 9500"
    assert "tests/test_pricing.py:18: AssertionError" in case.details


def test_failure_wins_when_case_has_failure_and_error():
    case = parse_junit(FIXTURES / "junit_mixed.xml").failed[2]
    assert case.outcome == "failed"
    assert case.message == "assert 1 == 2"


def test_node_id_for_module_level_test():
    case = parse_junit(FIXTURES / "junit_mixed.xml").cases[0]
    assert case.node_id == "tests/test_pricing.py::test_ok"


def test_node_id_for_test_in_class():
    case = parse_junit(FIXTURES / "junit_mixed.xml").failed[1]
    assert case.node_id == "tests/test_orders.py::TestPlace::test_setup_breaks"


def test_all_passed_report_has_no_failed_cases():
    assert parse_junit(FIXTURES / "junit_all_passed.xml").failed == ()


def test_bare_testsuite_root_is_accepted():
    report = parse_junit_bytes(b'<testsuite><testcase classname="t.test_a" name="test_x"/></testsuite>')
    assert report.cases[0].node_id == "t/test_a.py::test_x"


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"not xml at all",
        b"<testsuites><testsuite>",
        b"<html><body/></html>",
    ],
)
def test_unreadable_input_raises_parse_error(data):
    with pytest.raises(JUnitParseError):
        parse_junit_bytes(data)


def test_entity_declarations_are_rejected():
    data = b'<!DOCTYPE x [<!ENTITY a "aaaa">]><testsuites>&a;</testsuites>'
    with pytest.raises(JUnitParseError, match="DTD"):
        parse_junit_bytes(data)
