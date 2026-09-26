from aiterm.core.diagnosis import diagnose
from aiterm.core.models import Category, Diagnostic


def make_diag(raw="", category="UNKNOWN", file="test.py", line=1):
    return Diagnostic(
        file=file,
        line=line,
        column=0,
        severity="error",
        category=category,
        message="Command failed with exit code 1",
        source="test",
        raw=raw,
    )


def test_yaml_configuration_diagnosis():
    d = make_diag(
        file="config/bad.yaml",
        line=3,
        raw=(
            "Invalid configuration: config/bad.yaml: invalid YAML at line 3, "
            "column 1: expected ',' or ']', but got '<stream end>'"
        ),
    )

    result = diagnose(d)

    assert result.category == Category.CONFIGURATION_ERROR.value
    assert result.cause == "malformed YAML configuration"
    assert result.confidence == "high"
    assert "invalid YAML" in result.evidence
    assert "parser expected a closing bracket" in result.evidence
    assert "parser expected a comma" in result.evidence
    assert "parser reported an error at line 3" in result.evidence
    assert "config/bad.yaml" in result.verification


def test_syntax_diagnosis():
    result = diagnose(make_diag(raw="SyntaxError: invalid syntax"))

    assert result.category == Category.SYNTAX_ERROR.value
    assert result.confidence == "high"
    assert "syntax error" in result.cause


def test_type_diagnosis():
    result = diagnose(make_diag(raw="TypeError: unsupported operand type"))

    assert result.category == Category.TYPE_ERROR.value
    assert result.confidence == "high"


def test_import_diagnosis():
    result = diagnose(make_diag(raw="ModuleNotFoundError: No module named 'foo'"))

    assert result.category == Category.IMPORT_ERROR.value
    assert result.confidence == "high"


def test_dependency_diagnosis():
    result = diagnose(make_diag(raw="No module named 'requests'"))

    assert result.category == Category.DEPENDENCY_ERROR.value
    assert result.confidence == "high"


def test_runtime_diagnosis():
    result = diagnose(
        make_diag(
            raw="Traceback (most recent call last):\nNameError: name 'x' is not defined"
        )
    )

    assert result.category == Category.RUNTIME_ERROR.value
    assert result.confidence == "high"


def test_test_failure_diagnosis():
    result = diagnose(make_diag(raw="FAILED tests/test_engine.py::test_example"))

    assert result.category == Category.TEST_FAILURE.value
    assert result.confidence == "high"


def test_unknown_diagnosis():
    result = diagnose(make_diag(raw="Something unexpected happened"))

    assert result.category == Category.UNKNOWN.value
    assert result.confidence == "low"
    assert result.evidence == []
    assert "insufficient deterministic evidence" in result.cause
