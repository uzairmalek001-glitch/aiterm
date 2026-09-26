from aiterm.core.classifier import classify
from aiterm.core.models import Category, Diagnostic


def make_diag(message="", raw="", category="UNKNOWN"):
    return Diagnostic(
        file="test.py",
        line=1,
        column=0,
        severity="error",
        category=category,
        message=message,
        source="test",
        raw=raw,
    )


def test_invalid_yaml_is_configuration_error():
    d = make_diag(
        message="Command failed with exit code 1",
        raw="Invalid configuration: config/bad.yaml: invalid YAML at line 3",
    )
    assert classify(d) == Category.CONFIGURATION_ERROR.value


def test_syntax_error():
    d = make_diag(raw="SyntaxError: invalid syntax")
    assert classify(d) == Category.SYNTAX_ERROR.value


def test_type_error():
    d = make_diag(raw="TypeError: unsupported operand type")
    assert classify(d) == Category.TYPE_ERROR.value


def test_import_error():
    d = make_diag(raw="ModuleNotFoundError: No module named 'foo'")
    assert classify(d) == Category.IMPORT_ERROR.value


def test_dependency_error():
    d = make_diag(raw="No module named 'requests'")
    assert classify(d) == Category.DEPENDENCY_ERROR.value


def test_runtime_error():
    d = make_diag(raw="Traceback (most recent call last):\nNameError: name 'x' is not defined")
    assert classify(d) == Category.RUNTIME_ERROR.value


def test_test_failure():
    d = make_diag(raw="FAILED tests/test_engine.py::test_example")
    assert classify(d) == Category.TEST_FAILURE.value


def test_unknown_stays_unknown():
    d = make_diag(raw="Something went wrong")
    assert classify(d) == Category.UNKNOWN.value


def test_existing_category_is_preserved():
    d = make_diag(
        raw="SyntaxError: invalid syntax",
        category=Category.RUNTIME_ERROR.value,
    )
    assert classify(d) == Category.RUNTIME_ERROR.value
