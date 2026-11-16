import ci_failure_analyzer


def test_package_exposes_version():
    assert ci_failure_analyzer.__version__ == "0.1.0"
