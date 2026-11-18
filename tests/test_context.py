import inspect

import pytest

from ci_failure_analyzer.analysis import context as context_module
from ci_failure_analyzer.analysis.context import (
    MAX_FILE_LINES,
    MAX_FILES,
    MAX_LOG_LINES,
    METHOD_A,
    METHOD_B,
    REASON_CONFTEST,
    REASON_TEST_FILE,
    REASON_TRACEBACK,
    build_context,
    select_files,
)
from ci_failure_analyzer.inputs.junit import parse_junit_bytes
from ci_failure_analyzer.inputs.reader import BundleReader, clean_log_line
from ci_failure_analyzer.report.citations import check_citations
from ci_failure_analyzer.report.schema import parse_report

TRACEBACK = """def test_total():
>       assert total(cart) == 3

tests/unit/test_cart.py:5:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
/home/runner/work/repo/repo/src/shop/cart.py:9: in total
    return price(item)
src/shop/price.py:2: KeyError
/opt/python/lib/python3.12/site-packages/pluggy/_callers.py:77: in _multicall
"""

JUNIT = f"""<testsuites><testsuite>
<testcase classname="tests.unit.test_cart" name="test_total"><failure message="KeyError: 'x'">{TRACEBACK}</failure></testcase>
<testcase classname="tests.unit.test_cart" name="test_ok"/>
</testsuite></testsuites>
"""

CODE = {
    "src/shop/cart.py": "def total(cart):\n    return 1\n",
    "src/shop/price.py": "def price(item):\n    return table[item]\n",
    "src/shop/unused.py": "x = 1\n",
    "tests/conftest.py": "# root conftest\n",
    "tests/unit/conftest.py": "# unit conftest\n",
    "tests/unit/test_cart.py": "def test_total():\n    assert total(cart) == 3\n",
    "_callers.py": "# same file name as a site-packages module\n",
}

LOG = (
    "pytest\tInstall\t﻿2026-11-17T00:00:01.0000000Z installing\n"
    "pytest\tRun tests\t2026-11-17T00:00:02.0000000Z \x1b[31mE   KeyError: 'x'\x1b[0m\n"
)


@pytest.fixture
def junit():
    return parse_junit_bytes(JUNIT.encode())


@pytest.fixture
def reader(make_bundle):
    return BundleReader(make_bundle(LOG, CODE, junit=JUNIT))


def test_clean_log_line_removes_prefix_timestamp_and_colour():
    assert clean_log_line(LOG.split("\n")[1]) == ("Run tests", "E   KeyError: 'x'")
    assert clean_log_line(LOG.split("\n")[0]) == ("Install", "installing")
    assert clean_log_line("no tabs here") == ("", "no tabs here")
    assert clean_log_line("job\tstep\t^[[36;1mpytest -rA^[[0m") == ("step", "pytest -rA")


def test_selection_follows_the_fixed_rule_and_order(reader, junit):
    selected, omitted = select_files(reader, junit)
    assert [(f.path, f.reason) for f in selected] == [
        ("tests/unit/test_cart.py", REASON_TEST_FILE),
        ("src/shop/cart.py", REASON_TRACEBACK),
        ("src/shop/price.py", REASON_TRACEBACK),
        ("tests/unit/conftest.py", REASON_CONFTEST),
    ]
    assert omitted == []


def test_files_outside_the_repository_are_not_selected(reader, junit):
    paths = [f.path for f in select_files(reader, junit)[0]]
    assert "_callers.py" not in paths
    assert "src/shop/unused.py" not in paths
    assert "tests/conftest.py" not in paths


def test_selection_is_limited_and_reports_what_was_left_out(make_bundle):
    names = [f"tests/test_m{i}.py" for i in range(MAX_FILES + 2)]
    cases = "".join(f'<testcase classname="tests.test_m{i}" name="t"><failure message="x"/></testcase>' for i in range(MAX_FILES + 2))
    junit_xml = f"<testsuites><testsuite>{cases}</testsuite></testsuites>"
    reader = BundleReader(make_bundle(LOG, {name: "x = 1\n" for name in names}, junit=junit_xml))
    selected, omitted = select_files(reader, parse_junit_bytes(junit_xml.encode()))
    assert [f.path for f in selected] == names[:MAX_FILES]
    assert [f.path for f in omitted] == names[MAX_FILES:]


def test_selection_does_not_use_labels():
    # The rule sees only the bundle: its inputs are a reader and a JUnit report,
    # and the module never mentions the evaluation folders.
    assert list(inspect.signature(select_files).parameters) == ["reader", "junit"]
    source = inspect.getsource(context_module)
    assert "evals" not in source and "labels/" not in source


def test_method_a_has_log_and_run_information_but_no_code(reader, junit):
    context = build_context(reader, junit, METHOD_A)
    assert context.provided_code_paths == ()
    assert "    2| E   KeyError: 'x'" in context.text
    assert "--- step: Run tests (failed) ---" in context.text
    assert "tests/unit/test_cart.py::test_total [failed] KeyError: 'x'" in context.text
    assert "python: Python 3.12.16" in context.text
    assert "return table[item]" not in context.text
    assert (context.log_lines_total, context.log_lines_included) == (2, 2)


def test_method_b_adds_numbered_code_files(reader, junit):
    context = build_context(reader, junit, METHOD_B)
    assert context.provided_code_paths == (
        "tests/unit/test_cart.py",
        "src/shop/cart.py",
        "src/shop/price.py",
        "tests/unit/conftest.py",
    )
    assert "### src/shop/price.py (selected by: traceback; lines 1-2 of 2)" in context.text
    assert "    2|     return table[item]" in context.text
    assert context.text.startswith(build_context(reader, junit, METHOD_A).text)


def test_context_is_deterministic(reader, junit):
    assert build_context(reader, junit, METHOD_B) == build_context(reader, junit, METHOD_B)


def test_unknown_method_is_rejected(reader, junit):
    with pytest.raises(ValueError):
        build_context(reader, junit, "C")


def test_long_log_keeps_the_end_of_failed_steps(make_bundle, junit):
    install = "".join(f"pytest\tInstall\tinstall {i}\n" for i in range(MAX_LOG_LINES))
    tests = "".join(f"pytest\tRun tests\ttest {i}\n" for i in range(MAX_LOG_LINES + 10))
    reader = BundleReader(make_bundle(install + tests, CODE, junit=JUNIT))
    context = build_context(reader, junit, METHOD_A)
    assert context.log_lines_included == MAX_LOG_LINES
    assert "install 0" not in context.text
    assert f"{2 * MAX_LOG_LINES + 10:>5}| test {MAX_LOG_LINES + 9}" in context.text
    assert f"[{MAX_LOG_LINES + 10} lines omitted]" in context.text


def test_long_file_is_truncated_and_recorded(make_bundle, junit):
    code = dict(CODE)
    code["src/shop/cart.py"] = "".join(f"line{i} = {i}\n" for i in range(MAX_FILE_LINES + 5))
    context = build_context(BundleReader(make_bundle(LOG, code, junit=JUNIT)), junit, METHOD_B)
    assert context.truncated_files == ("src/shop/cart.py",)
    assert f"lines 1-{MAX_FILE_LINES} of {MAX_FILE_LINES + 5}" in context.text
    assert f"line{MAX_FILE_LINES} = " not in context.text


def test_line_numbers_in_context_match_the_citation_checker(reader, junit):
    context = build_context(reader, junit, METHOD_B)
    report = parse_report(
        {
            "conclusion": "cause_candidate",
            "observed_facts": [{"statement": "KeyError in the log", "evidence_ids": ["E1"]}],
            "cause_candidates": [{"summary": "s", "reasoning": "r", "confidence": "low", "evidence_ids": ["E2"]}],
            "evidence": [
                {"id": "E1", "source": "log", "path": "job.log", "start_line": 2, "end_line": 2, "quote": "E   KeyError: 'x'"},
                {"id": "E2", "source": "code", "path": "src/shop/price.py", "start_line": 2, "end_line": 2,
                 "quote": "return table[item]"},
            ],
            "verification_steps": [{"description": "rerun"}],
        }
    )
    assert check_citations(report, reader, context.provided_code_paths) == []


BRANCH_LOG = (
    "pytest\tCheckout\t * [new ref] abc -> origin/case/x\n"
    "pytest\tCheckout\tSwitched to a new branch 'case/x'\n"
    "pytest\tRun tests\ttests/case/x/test_a.py::test_one FAILED\n"
    "pytest\tRun tests\tcase/x-ray and showcase/x are other names\n"
)


def test_branch_name_is_masked_in_log_lines_but_not_inside_other_names(make_bundle):
    reader = BundleReader(make_bundle(BRANCH_LOG, CODE, junit=JUNIT))
    assert reader.lines("job.log") == [
        " * [new ref] abc -> origin/<branch>",
        "Switched to a new branch '<branch>'",
        "tests/case/x/test_a.py::test_one FAILED",
        "case/x-ray and showcase/x are other names",
    ]


def test_context_does_not_contain_the_branch_name(make_bundle, junit):
    reader = BundleReader(make_bundle(BRANCH_LOG, CODE, junit=JUNIT))
    text = build_context(reader, junit, METHOD_B).text
    assert "branch: " not in text
    assert "origin/case/x" not in text and "'case/x'" not in text


def test_quote_of_a_masked_line_passes_the_citation_check(make_bundle):
    reader = BundleReader(make_bundle(BRANCH_LOG, CODE, junit=JUNIT))
    report = parse_report(
        {
            "conclusion": "cause_candidate",
            "observed_facts": [{"statement": "s", "evidence_ids": ["E1"]}],
            "cause_candidates": [{"summary": "s", "reasoning": "r", "confidence": "low", "evidence_ids": ["E1"]}],
            "evidence": [
                {
                    "id": "E1",
                    "source": "log",
                    "path": "job.log",
                    "start_line": 2,
                    "end_line": 2,
                    "quote": "Switched to a new branch '<branch>'",
                }
            ],
            "verification_steps": [{"description": "d"}],
        }
    )
    assert check_citations(report, reader) == []
