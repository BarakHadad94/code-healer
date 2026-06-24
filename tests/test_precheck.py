import subprocess
from unittest.mock import MagicMock, patch

from backend.precheck import PrecheckResult, _run_pytest_sync, _run_ruff_sync


def _fake_proc(returncode, stdout="", stderr=""):
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


# --- _run_pytest_sync ---

def test_pytest_missing_workspace(tmp_path):
    result = _run_pytest_sync(str(tmp_path / "nonexistent"), 30)
    assert result.passed is False
    assert "not found" in result.output.lower()
    assert result.exit_code == -1


def test_pytest_passes(tmp_path):
    with patch("backend.precheck.subprocess.run", return_value=_fake_proc(0, stdout="1 passed")):
        result = _run_pytest_sync(str(tmp_path), 30)
    assert result.passed is True
    assert result.exit_code == 0
    assert "1 passed" in result.output


def test_pytest_fails(tmp_path):
    with patch("backend.precheck.subprocess.run", return_value=_fake_proc(1, stdout="1 failed")):
        result = _run_pytest_sync(str(tmp_path), 30)
    assert result.passed is False
    assert result.exit_code == 1
    assert "[exit 1]" in result.output


def test_pytest_timeout(tmp_path):
    with patch(
        "backend.precheck.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="pytest", timeout=5),
    ):
        result = _run_pytest_sync(str(tmp_path), 5)
    assert result.passed is False
    assert "timed out" in result.output
    assert result.exit_code == -1


def test_pytest_interpreter_not_found(tmp_path):
    with patch("backend.precheck.subprocess.run", side_effect=FileNotFoundError):
        result = _run_pytest_sync(str(tmp_path), 30)
    assert result.passed is False
    assert "not found" in result.output.lower()
    assert result.exit_code == -1


def test_pytest_output_combines_stdout_and_stderr(tmp_path):
    with patch(
        "backend.precheck.subprocess.run",
        return_value=_fake_proc(0, stdout="stdout part", stderr="stderr part"),
    ):
        result = _run_pytest_sync(str(tmp_path), 30)
    assert "stdout part" in result.output
    assert "stderr part" in result.output


# --- _run_ruff_sync ---

def test_ruff_missing_workspace(tmp_path):
    result = _run_ruff_sync(str(tmp_path / "nonexistent"), 30)
    assert result.passed is False
    assert result.exit_code == -1


def test_ruff_passes(tmp_path):
    with patch("backend.precheck.subprocess.run", return_value=_fake_proc(0)):
        result = _run_ruff_sync(str(tmp_path), 30)
    assert result.passed is True
    assert result.exit_code == 0


def test_ruff_fails(tmp_path):
    with patch(
        "backend.precheck.subprocess.run",
        return_value=_fake_proc(1, stdout="E501 line too long"),
    ):
        result = _run_ruff_sync(str(tmp_path), 30)
    assert result.passed is False
    assert result.exit_code == 1


def test_ruff_timeout(tmp_path):
    with patch(
        "backend.precheck.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="ruff", timeout=5),
    ):
        result = _run_ruff_sync(str(tmp_path), 5)
    assert result.passed is False
    assert "timed out" in result.output
    assert result.exit_code == -1


def test_ruff_not_installed(tmp_path):
    with patch("backend.precheck.subprocess.run", side_effect=FileNotFoundError):
        result = _run_ruff_sync(str(tmp_path), 30)
    assert result.passed is False
    assert "not found" in result.output.lower()
    assert result.exit_code == -1
