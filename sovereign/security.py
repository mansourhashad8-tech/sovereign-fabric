"""Openness and vulnerability disclosure as executable checks.

The scanner is deliberately conservative: it flags patterns that deserve a
human look, not proven exploits. Every finding carries a rule, a location, and
a remediation. The dependency inventory resolves direct and transitive
requirements and classifies their licences. OSV is queried online when asked;
when it is not, the report says the check was not performed.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import time
import tomllib
import urllib.request
from dataclasses import asdict, dataclass
from importlib import metadata
from pathlib import Path
from typing import Any, Iterable

from .models import utcnow

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
_OPEN_LICENSES = (
    "mit", "apache", "bsd", "gpl", "lgpl", "psf", "python software",
    "isc", "mozilla", "mpl", "unlicense", "cc0", "public domain",
)
_SECRET = re.compile(
    r"(?i)\b(api[_-]?key|secret|password|passwd|token)\b\s*=\s*['\"]([A-Za-z0-9_\-]{16,})['\"]"
)
_HTTP = re.compile("http" + r"://[^\s'\"]+")


@dataclass
class Finding:
    rule: str
    severity: str
    path: str
    line: int
    message: str
    snippet: str
    remediation: str
    status: str = "open"


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _keyword(node: ast.Call, name: str) -> ast.AST | None:
    for keyword in node.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


class _Visitor(ast.NodeVisitor):
    def __init__(self, path: Path, lines: list[str], findings: list[Finding]) -> None:
        self.path = path
        self.lines = lines
        self.findings = findings

    def _add(self, rule: str, severity: str, line: int, message: str, remediation: str) -> None:
        snippet = self.lines[line - 1].strip() if 0 < line <= len(self.lines) else ""
        self.findings.append(
            Finding(rule, severity, str(self.path), line, message, snippet, remediation)
        )

    def visit_Call(self, node: ast.Call) -> None:
        name = _dotted(node.func)
        if name in {"eval", "exec"}:
            self._add(
                "dynamic-code", "high", node.lineno,
                f"{name}() executes dynamic code in-process.",
                "Replace with a whitelisted evaluator or run it in a sandboxed subprocess.",
            )
        if name in {"os.system", "os.popen"}:
            self._add(
                "os-command", "high", node.lineno,
                f"{name}() passes a command to a shell.",
                "Use subprocess with an argument list, shell=False, and a timeout.",
            )
        if name.startswith("subprocess."):
            shell = _keyword(node, "shell")
            if isinstance(shell, ast.Constant) and shell.value is True:
                self._add(
                    "shell-true", "high", node.lineno,
                    "subprocess is called with shell=True.",
                    "Pass an argument list and keep shell=False.",
                )
            if _keyword(node, "timeout") is None:
                self._add(
                    "no-timeout", "medium", node.lineno,
                    "subprocess is called without a timeout.",
                    "Add a finite timeout so a child cannot hang the parent.",
                )
        if name in {"pickle.load", "pickle.loads", "marshal.loads"}:
            self._add(
                "unsafe-deserialization", "high", node.lineno,
                f"{name}() can execute arbitrary code from untrusted bytes.",
                "Use JSON or a schema-validated format for untrusted data.",
            )
        if name in {"hashlib.md5", "hashlib.sha1"}:
            self._add(
                "weak-hash", "medium", node.lineno,
                f"{name}() is not collision-resistant.",
                "Use SHA-256 for identifiers and signatures; keep MD5/SHA-1 only for legacy interop.",
            )
        if name == "tempfile.mktemp":
            self._add(
                "insecure-tempfile", "medium", node.lineno,
                "tempfile.mktemp() is race-prone.",
                "Use tempfile.mkstemp() or TemporaryDirectory().",
            )
        verify = _keyword(node, "verify")
        if isinstance(verify, ast.Constant) and verify.value is False:
            self._add(
                "tls-verify-disabled", "high", node.lineno,
                "TLS certificate verification is disabled.",
                "Remove verify=False; fix the trust store instead.",
            )
        if name in {"yaml.load", "yaml.unsafe_load"}:
            loader = _keyword(node, "Loader")
            safe = isinstance(loader, ast.Attribute) and loader.attr == "SafeLoader"
            if not safe:
                self._add(
                    "unsafe-yaml", "high", node.lineno,
                    "yaml.load() without SafeLoader can construct arbitrary objects.",
                    "Use yaml.safe_load() or Loader=yaml.SafeLoader.",
                )
        if name.endswith(".execute") or name.endswith(".executemany"):
            for argument in node.args:
                dynamic = isinstance(argument, ast.JoinedStr) or (
                    isinstance(argument, ast.BinOp)
                    and isinstance(argument.op, (ast.Add, ast.Mod))
                )
                if dynamic:
                    self._add(
                        "sql-string-build", "high", node.lineno,
                        "SQL is built from a dynamic expression.",
                        "Use parameterized queries; never interpolate values into SQL.",
                    )
                    break
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
            self._add(
                "swallowed-error", "low", node.lineno,
                "An exception is swallowed with pass.",
                "Log the error or narrow the exception type.",
            )
        self.generic_visit(node)


def scan_source(root: str | Path = "sovereign") -> list[Finding]:
    base = Path(root)
    files = [base] if base.is_file() else sorted(base.rglob("*.py"))
    findings: list[Finding] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        lines = text.splitlines()
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            findings.append(
                Finding(
                    "parse-error", "medium", str(path), exc.lineno or 0,
                    f"Could not parse: {exc.msg}", "", "Fix the syntax error before auditing.",
                )
            )
            continue
        _Visitor(path, lines, findings).visit(tree)
        for number, line in enumerate(lines, 1):
            secret = _SECRET.search(line)
            if secret and not re.search(r"example|dummy|test|your[_-]?|xxx", secret.group(2), re.I):
                findings.append(
                    Finding(
                        "hardcoded-secret", "high", str(path), number,
                        f"A literal value is assigned to {secret.group(1)}.",
                        line.strip(),
                        "Read secrets from the environment or a secret manager.",
                    )
                )
            if _HTTP.search(line) and "www.w3.org" not in line:
                findings.append(
                    Finding(
                        "plaintext-http", "medium", str(path), number,
                        "A plaintext http:// URL is present.",
                        line.strip(),
                        "Use https:// and verify the certificate.",
                    )
                )
    unique: dict[tuple[str, str, int], Finding] = {}
    for finding in findings:
        unique[(finding.rule, finding.path, finding.line)] = finding
    return sorted(
        unique.values(),
        key=lambda item: (_SEVERITY_ORDER.get(item.severity, 9), item.path, item.line),
    )


def _license_of(dist: metadata.Distribution) -> str:
    expression = dist.metadata.get("License-Expression")
    if expression:
        return expression.strip()
    value = (dist.metadata.get("License") or "").strip()
    if value and value.upper() != "UNKNOWN":
        return value
    for classifier in dist.metadata.get_all("Classifier") or []:
        if classifier.startswith("License ::"):
            return classifier.split("::")[-1].strip()
    return ""


def _is_open(license_text: str) -> bool:
    lowered = license_text.lower()
    return any(token in lowered for token in _OPEN_LICENSES)


def _direct_requirements() -> list[str]:
    path = Path("pyproject.toml")
    if not path.exists():
        return []
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    project = data.get("project", {})
    return list(project.get("dependencies", [])) + list(
        project.get("optional-dependencies", {}).get("dev", [])
    )


def _name_from_requirement(requirement: str) -> str:
    try:
        from packaging.requirements import Requirement

        return Requirement(requirement).name
    except Exception:
        return re.split(r"[<>=!~;\[\s]", requirement, maxsplit=1)[0].strip()


def _resolve_tree(names: Iterable[str]) -> set[str]:
    seen: set[str] = set()
    queue = list(names)
    while queue:
        name = queue.pop()
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue
        for requirement in dist.requires or []:
            try:
                from packaging.requirements import Requirement

                parsed = Requirement(requirement)
                if parsed.marker is not None and not parsed.marker.evaluate({"extra": ""}):
                    continue
                queue.append(parsed.name)
            except Exception:
                continue
    return seen


def dependency_inventory() -> list[dict[str, Any]]:
    direct = [_name_from_requirement(item) for item in _direct_requirements()]
    names = _resolve_tree(direct)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for name in sorted(names, key=str.lower):
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            rows.append(
                {
                    "name": name, "version": None, "license": "not installed",
                    "open_source": False, "direct": name in direct,
                }
            )
            continue
        license_text = _license_of(dist)
        rows.append(
            {
                "name": dist.metadata.get("Name") or name,
                "version": dist.version,
                "license": license_text or "unknown",
                "open_source": _is_open(license_text),
                "direct": (dist.metadata.get("Name") or name).lower() in {d.lower() for d in direct},
            }
        )
    return rows


def osv_query(dependencies: list[dict[str, Any]], timeout: float = 8.0) -> dict[str, Any]:
    queries = [
        {"package": {"name": row["name"], "ecosystem": "PyPI"}, "version": row["version"]}
        for row in dependencies
        if row.get("version")
    ]
    if not queries:
        return {"ok": False, "error": "no pinned versions to query", "vulnerabilities": []}
    request = urllib.request.Request(
        "https://api.osv.dev/v1/querybatch",
        data=json.dumps({"queries": queries}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.load(response)
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "vulnerabilities": []}
    found: list[dict[str, Any]] = []
    for row, result in zip(dependencies, data.get("results", [])):
        for vuln in result.get("vulns", []):
            found.append(
                {
                    "package": row["name"],
                    "version": row["version"],
                    "id": vuln.get("id"),
                    "aliases": vuln.get("aliases", []),
                    "summary": vuln.get("summary", ""),
                }
            )
    return {"ok": True, "vulnerabilities": found}


def _source_hashes(root: Path) -> list[dict[str, Any]]:
    files = [root] if root.is_file() else sorted(root.rglob("*.py"))
    rows = []
    for path in files:
        data = path.read_bytes()
        rows.append(
            {
                "path": str(path),
                "sha256": hashlib.sha256(data).hexdigest(),
                "lines": data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0),
            }
        )
    return rows


def _commit() -> str | None:
    head = Path(".git/HEAD")
    if not head.exists():
        return None
    value = head.read_text(encoding="utf-8").strip()
    if value.startswith("ref: "):
        ref = Path(".git") / value[5:]
        return ref.read_text(encoding="utf-8").strip() if ref.exists() else None
    return value or None


def audit(root: str | Path = "sovereign", online: bool = True) -> dict[str, Any]:
    started = time.monotonic()
    base = Path(root)
    findings = scan_source(base)
    dependencies = dependency_inventory()
    license_file = next(
        (name for name in ("LICENSE", "LICENSE.md", "COPYING") if Path(name).exists()), None
    )
    osv = osv_query(dependencies) if online else {
        "ok": False, "error": "online check disabled", "vulnerabilities": []
    }
    counts = {severity: 0 for severity in _SEVERITY_ORDER}
    for finding in findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1
    high_open = [f for f in findings if f.severity in {"critical", "high"} and f.status == "open"]
    unknown = [row for row in dependencies if not row["open_source"]]
    openness_passed = bool(license_file) and not unknown and not high_open
    security_passed = bool(osv.get("ok")) and not osv.get("vulnerabilities") and not high_open
    return {
        "generated_at": utcnow(),
        "commit": _commit(),
        "root": str(base),
        "duration_s": round(time.monotonic() - started, 3),
        "license_file": license_file,
        "source_files": _source_hashes(base),
        "findings": [asdict(finding) for finding in findings],
        "finding_counts": counts,
        "dependencies": dependencies,
        "unknown_licenses": [row["name"] for row in unknown],
        "vulnerability_check": osv,
        "openness_passed": openness_passed,
        "security_passed": security_passed,
        "passed": openness_passed and security_passed,
    }


def disclosure_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Security & Openness Disclosure",
        "",
        f"Generated: {report['generated_at']}",
        f"Commit: `{report.get('commit') or 'unknown'}`",
        f"Scope: `{report['root']}`",
        "",
        "This report is generated by the project's own scanner. It is a",
        "conservative pattern audit, not a proof of absence. The scanner and",
        "every finding are public, so anyone can reproduce or challenge them.",
        "",
        "## Summary",
        "",
        f"- Source files hashed: {len(report['source_files'])}",
        f"- Findings: {report['finding_counts']}",
        f"- License file: {report.get('license_file') or 'missing'}",
        f"- Unknown-license dependencies: {len(report['unknown_licenses'])}",
        f"- Vulnerability check: {'completed' if report['vulnerability_check'].get('ok') else 'not completed'}",
        f"- Openness: {'PASS' if report['openness_passed'] else 'REVIEW'}",
        f"- Security: {'PASS' if report['security_passed'] else 'REVIEW'}",
        "",
        "## Findings",
        "",
    ]
    if report["findings"]:
        lines += [
            "| Severity | Rule | Location | Finding | Remediation | Status |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for finding in report["findings"]:
            lines.append(
                f"| {finding['severity']} | `{finding['rule']}` | "
                f"`{finding['path']}:{finding['line']}` | {finding['message']} | "
                f"{finding['remediation']} | {finding['status']} |"
            )
    else:
        lines.append(
            "No findings from these rules. Absence of evidence is not evidence of absence."
        )
    lines += [
        "",
        "## Dependencies",
        "",
        "| Package | Version | License | Open source | Direct |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in report["dependencies"]:
        lines.append(
            f"| {row['name']} | {row['version'] or '-'} | {row['license']} | "
            f"{'yes' if row['open_source'] else 'NO'} | {'yes' if row['direct'] else 'no'} |"
        )
    lines += ["", "## Known vulnerabilities (OSV)", ""]
    check = report["vulnerability_check"]
    if not check.get("ok"):
        lines.append(f"Not checked: {check.get('error', 'unknown error')}.")
    elif not check["vulnerabilities"]:
        lines.append("OSV returned no known vulnerabilities for the resolved versions.")
    else:
        lines += ["| Package | Version | ID | Summary |", "| --- | --- | --- | --- |"]
        for vuln in check["vulnerabilities"]:
            lines.append(
                f"| {vuln['package']} | {vuln['version']} | {vuln['id']} | {vuln['summary']} |"
            )
    lines += [
        "",
        "## Responsible disclosure",
        "",
        "- Report security issues privately through the repository's Security",
        "  Advisories tab. Do not open a public issue with exploit details.",
        "- Include the affected commit, a reproduction, and the impact.",
        "- The maintainers will acknowledge, fix, and publish a disclosure report",
        "  with the fix and the prevention measure.",
        "",
        "## Limitations",
        "",
        "- Static rules can miss logic flaws and runtime vulnerabilities.",
        "- OSV is a snapshot of public advisories, not a guarantee.",
        "- No dynamic application security testing (DAST) is performed here.",
        "- This report does not certify the absence of vulnerabilities.",
        "",
    ]
    return "\n".join(lines)


def write_disclosure(path: str = "SECURITY_DISCLOSURE.md", online: bool = True) -> dict[str, Any]:
    report = audit(online=online)
    Path(path).write_text(disclosure_markdown(report), encoding="utf-8")
    return report


def write_manifest(path: str = "OPENNESS_MANIFEST.json", online: bool = True) -> dict[str, Any]:
    report = audit(online=online)
    Path(path).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def cyclonedx_sbom(report: dict[str, Any] | None = None) -> dict[str, Any]:
    report = report or audit(online=False)
    components = []
    for row in report["dependencies"]:
        version = row["version"] or ""
        purl = f"pkg:pypi/{row['name'].lower()}@{version}" if version else f"pkg:pypi/{row['name'].lower()}"
        component: dict[str, Any] = {
            "type": "library",
            "bom-ref": purl,
            "name": row["name"],
            "version": version,
            "purl": purl,
        }
        if row["license"] and row["license"] != "unknown":
            component["licenses"] = [{"license": {"name": row["license"]}}]
        components.append(component)
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "timestamp": report["generated_at"],
            "tools": [
                {"vendor": "sovereign-fabric", "name": "security.py", "version": "0.1.0"}
            ],
            "component": {
                "type": "application",
                "bom-ref": "pkg:pypi/sovereign-fabric@0.1.0",
                "name": "sovereign-fabric",
                "version": "0.1.0",
            },
        },
        "components": components,
    }


def write_sbom(path: str = "sbom.cdx.json", online: bool = False) -> dict[str, Any]:
    sbom = cyclonedx_sbom(audit(online=online))
    Path(path).write_text(json.dumps(sbom, indent=2, ensure_ascii=False), encoding="utf-8")
    return sbom
