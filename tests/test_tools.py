import inspect
import io
import tarfile

import pytest

from ci_failure_analyzer.analysis import tools as tools_module
from ci_failure_analyzer.analysis.tools import (
    MAX_READ_LINES,
    MAX_SEARCH_MATCHES,
    TOOL_DEFINITIONS,
    TOOL_LIST_FILES,
    TOOL_READ_FILE,
    TOOL_SEARCH_CODE,
    ToolSession,
)
from ci_failure_analyzer.inputs.reader import BundleReader

CODE = {
    "src/shop/cart.py": "def total(cart):\n    return sum(cart)\n",
    "src/shop/long.py": "".join(f"value_{n} = {n}\n" for n in range(1, 451)),
    "tests/test_cart.py": "from shop.cart import total\n\n\ndef test_total():\n    assert total([1, 2]) == 3\n",
}
LOG = "pytest\tRun tests\t2026-11-17T00:00:00.0000000Z FAILED tests/test_cart.py::test_total\n"
JUNIT = "<testsuites/>\n"


@pytest.fixture
def bundle(make_bundle):
    return make_bundle(LOG, CODE, JUNIT)


@pytest.fixture
def session(bundle):
    return ToolSession(BundleReader(bundle))


def test_list_files_shows_snapshot_paths_with_line_counts(session):
    result = session.call(TOOL_LIST_FILES, {})
    assert not result.is_error
    assert result.text.splitlines() == [
        "src/shop/cart.py (2 lines)",
        "src/shop/long.py (450 lines)",
        "tests/test_cart.py (5 lines)",
    ]
    assert session.call(TOOL_LIST_FILES, {"prefix": "tests/"}).text == "tests/test_cart.py (5 lines)"
    assert session.call(TOOL_LIST_FILES, {"prefix": "docs/"}).is_error


def test_read_file_numbers_lines_like_the_citation_checker(session, bundle):
    result = session.call(TOOL_READ_FILE, {"path": "tests/test_cart.py", "start_line": 4, "end_line": 5})
    assert result.text.splitlines() == [
        "### tests/test_cart.py (lines 4-5 of 5)",
        "    4| def test_total():",
        "    5|     assert total([1, 2]) == 3",
    ]
    assert BundleReader(bundle).lines("tests/test_cart.py")[3] == "def test_total():"
    assert session.seen_lines("tests/test_cart.py") == {4, 5}


def test_read_file_stops_at_the_line_limit_and_says_so(session):
    result = session.call(TOOL_READ_FILE, {"path": "src/shop/long.py", "start_line": 11})
    lines = result.text.splitlines()
    assert lines[0] == f"### src/shop/long.py (lines 11-{10 + MAX_READ_LINES} of 450)"
    assert len(lines) == MAX_READ_LINES + 2
    assert "more lines follow" in lines[-1]
    assert session.seen_lines("src/shop/long.py") == set(range(11, 11 + MAX_READ_LINES))


def test_read_file_can_read_the_log_and_junit_but_no_other_bundle_file(session):
    assert "FAILED tests/test_cart.py::test_total" in session.call(TOOL_READ_FILE, {"path": "job.log"}).text
    assert not session.call(TOOL_READ_FILE, {"path": "reports/junit.xml"}).is_error
    for path in ("run.json", "manifest.json", "code.tar", "reports/checkout_sha.txt"):
        assert session.call(TOOL_READ_FILE, {"path": path}).is_error, path


@pytest.mark.parametrize(
    "path",
    [
        "../run.json",
        "src/../../run.json",
        "src/shop/../shop/cart.py",
        "../../evals/answers/case-001.json",
        "/etc/passwd",
        "C:/Windows/win.ini",
        "C:\\Windows\\win.ini",
        "\\\\server\\share\\file.txt",
        "file:///etc/passwd",
        "~/.ssh/id_rsa",
        ".git/config",
        ".env",
        "",
    ],
)
def test_paths_outside_the_snapshot_are_refused(session, path):
    result = session.call(TOOL_READ_FILE, {"path": path})
    assert result.is_error
    assert session.seen_paths == ()
    assert session.call(TOOL_LIST_FILES, {"prefix": path or ".."}).is_error


def test_existing_files_outside_the_bundle_are_not_reachable(make_bundle, tmp_path):
    """A real file next to the bundle, reached by a relative or an absolute path, stays unreadable."""
    bundle = make_bundle(LOG, CODE, JUNIT)
    secret = tmp_path / "answer.json"
    secret.write_text('{"root_cause": "secret"}', encoding="utf-8")
    session = ToolSession(BundleReader(bundle))
    for path in ("../answer.json", str(secret), secret.as_posix(), secret.as_uri()):
        result = session.call(TOOL_READ_FILE, {"path": path})
        assert result.is_error and "secret" not in result.text, path
    assert "secret" not in session.call(TOOL_SEARCH_CODE, {"query": "root_cause"}).text
    assert "answer.json" not in session.call(TOOL_LIST_FILES, {}).text


def test_links_and_special_members_in_the_snapshot_are_not_followed(make_bundle, tmp_path):
    bundle = make_bundle(LOG, CODE, JUNIT)
    secret = tmp_path / "answer.json"
    secret.write_text("secret", encoding="utf-8")
    with tarfile.open(bundle / "code.tar", "a") as tar:
        for name, kind in (("link_out", tarfile.SYMTYPE), ("hard_out", tarfile.LNKTYPE)):
            info = tarfile.TarInfo(name)
            info.type = kind
            info.linkname = str(secret)
            tar.addfile(info)
        info = tarfile.TarInfo("../escape.py")
        data = b"escaped = True\n"
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    session = ToolSession(BundleReader(bundle))
    listing = session.call(TOOL_LIST_FILES, {}).text
    assert "link_out" not in listing and "hard_out" not in listing
    assert session.call(TOOL_READ_FILE, {"path": "link_out"}).is_error
    assert session.call(TOOL_READ_FILE, {"path": "hard_out"}).is_error
    # A member whose name climbs out is only a name inside the archive: nothing is extracted to disk.
    assert not (bundle.parent / "escape.py").exists()


def test_search_finds_plain_text_and_records_matched_lines(session):
    result = session.call(TOOL_SEARCH_CODE, {"query": " total"})
    assert result.text.splitlines() == [
        "src/shop/cart.py:1| def total(cart):",
        "tests/test_cart.py:1| from shop.cart import total",
        "tests/test_cart.py:5|     assert total([1, 2]) == 3",
    ]
    assert session.seen_lines("src/shop/cart.py") == {1}
    assert session.seen_lines("tests/test_cart.py") == {1, 5}
    assert session.call(TOOL_SEARCH_CODE, {"query": " total", "prefix": "src/"}).text == "src/shop/cart.py:1| def total(cart):"
    # The query is text, not a pattern.
    assert session.call(TOOL_SEARCH_CODE, {"query": "t.tal"}).text.startswith("no line")


def test_search_does_not_cover_the_log_or_other_bundle_files(session):
    assert session.call(TOOL_SEARCH_CODE, {"query": "FAILED"}).text.startswith("no line")
    assert session.call(TOOL_SEARCH_CODE, {"query": "headBranch"}).text.startswith("no line")


def test_search_is_limited_and_reports_what_was_left_out(session):
    result = session.call(TOOL_SEARCH_CODE, {"query": "value_"})
    lines = result.text.splitlines()
    assert len(lines) == MAX_SEARCH_MATCHES + 1
    assert lines[-1].startswith(f"[{450 - MAX_SEARCH_MATCHES} more matching lines")
    assert len(session.seen_lines("src/shop/long.py")) == MAX_SEARCH_MATCHES


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("delete_file", {"path": "src/shop/cart.py"}),
        (TOOL_READ_FILE, None),
        (TOOL_READ_FILE, ["src/shop/cart.py"]),
        (TOOL_READ_FILE, {}),
        (TOOL_READ_FILE, {"path": 3}),
        (TOOL_READ_FILE, {"path": "src/shop/cart.py", "start_line": 0}),
        (TOOL_READ_FILE, {"path": "src/shop/cart.py", "start_line": "1"}),
        (TOOL_READ_FILE, {"path": "src/shop/cart.py", "start_line": True}),
        (TOOL_READ_FILE, {"path": "src/shop/cart.py", "start_line": 2, "end_line": 1}),
        (TOOL_READ_FILE, {"path": "src/shop/cart.py", "start_line": 3}),
        (TOOL_SEARCH_CODE, {}),
        (TOOL_SEARCH_CODE, {"query": "  "}),
        (TOOL_SEARCH_CODE, {"query": "a\nb"}),
        (TOOL_SEARCH_CODE, {"query": "x" * 201}),
        (TOOL_SEARCH_CODE, {"query": "total", "prefix": 1}),
        (TOOL_LIST_FILES, {"prefix": ["src"]}),
    ],
)
def test_bad_calls_return_an_error_instead_of_raising(session, name, arguments):
    result = session.call(name, arguments)
    assert result.is_error
    assert session.calls[-1]["is_error"]
    assert session.seen_paths == ()


def test_call_limit_counts_errors_and_refuses_further_calls(bundle):
    session = ToolSession(BundleReader(bundle), max_calls=3)
    session.call(TOOL_LIST_FILES, {})
    session.call(TOOL_READ_FILE, {"path": "missing.py"})
    session.call(TOOL_READ_FILE, {"path": "src/shop/cart.py"})
    assert session.calls_left == 0
    refused = session.call(TOOL_READ_FILE, {"path": "tests/test_cart.py"})
    assert refused.is_error and "limit" in refused.text
    assert len(session.calls) == 3 and session.refused_calls == 1
    assert session.seen_paths == ("src/shop/cart.py",)
    assert [c["name"] for c in session.calls] == [TOOL_LIST_FILES, TOOL_READ_FILE, TOOL_READ_FILE]


def test_unreadable_file_is_listed_but_not_read(make_bundle):
    bundle = make_bundle(LOG, CODE | {"data.bin": "a\x00b"}, JUNIT)
    session = ToolSession(BundleReader(bundle))
    assert "data.bin (not readable as text)" in session.call(TOOL_LIST_FILES, {}).text
    assert session.call(TOOL_READ_FILE, {"path": "data.bin"}).is_error


def test_tool_definitions_match_the_implemented_tools():
    assert [d["name"] for d in TOOL_DEFINITIONS] == [TOOL_LIST_FILES, TOOL_READ_FILE, TOOL_SEARCH_CODE]
    for definition in TOOL_DEFINITIONS:
        assert definition["input_schema"]["additionalProperties"] is False
        assert definition["description"]


def test_tools_module_does_not_touch_the_file_system_itself():
    """All reading goes through BundleReader; the module has no way to open another path."""
    source = inspect.getsource(tools_module)
    for forbidden in ("open(", "pathlib", "import os", "subprocess", "read_text", "read_bytes", "glob("):
        assert forbidden not in source, forbidden
