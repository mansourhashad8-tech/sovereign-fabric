import pytest

from sovereign.programs import _evaluate
from sovereign.security import audit, disclosure_markdown, scan_source


def test_scanner_detects_dynamic_code_and_shell_true(tmp_path):
    path = tmp_path / "bad.py"
    path.write_text(
        "import subprocess\n"
        "def f(value):\n"
        "    eval('1 + 1')\n"
        "    subprocess.run('ls', shell=True)\n"
        "    return value\n"
    )
    rules = {finding.rule for finding in scan_source(tmp_path)}
    assert "dynamic-code" in rules
    assert "shell-true" in rules
    assert "no-timeout" in rules


def test_safe_evaluator_rejects_attribute_escape():
    with pytest.raises(ValueError):
        _evaluate("value.__class__", "x")
    with pytest.raises(ValueError):
        _evaluate("__import__('os')", "x")


def test_project_audit_is_open_and_clean():
    report = audit(online=False)
    assert report["license_file"] == "LICENSE"
    assert report["finding_counts"]["high"] == 0
    assert report["finding_counts"]["critical"] == 0
    assert report["unknown_licenses"] == []
    assert report["openness_passed"] is True


def test_disclosure_has_required_sections():
    markdown = disclosure_markdown(audit(online=False))
    for section in (
        "# Security & Openness Disclosure",
        "## Findings",
        "## Dependencies",
        "## Known vulnerabilities (OSV)",
        "## Responsible disclosure",
        "## Limitations",
    ):
        assert section in markdown
