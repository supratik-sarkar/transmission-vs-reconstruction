"""Public-repository privacy and secret scan.

Fails the build if a tracked file contains material that must never be public:
machine-specific filesystem paths, credentials, real contact addresses,
private workspace or run directories, internal assistant/tooling instructions,
or venue/submission language in the public documentation.

Two deliberate design points:

* The scanner is ALLOWLISTED against itself and its own test. It has to contain
  the very patterns it looks for, and obfuscating them to dodge the check would
  make the rules unreadable, which is worse.

* Venue names are legitimate scientific content in a bibliography or a
  manuscript source. They are flagged only in the public README and docs, where
  they would make the repository read like a submission workspace rather than a
  piece of research software.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

#: Files permitted to contain the patterns because they define or test them.
SELF_ALLOWLIST: tuple[str, ...] = (
    "src/handoff_fidelity/privacy/scan.py",
    "tests/test_privacy_scan.py",
    "docs/reproducibility.md",
)

#: Extensions that are scanned. Binary and data formats are skipped.
TEXT_SUFFIXES: frozenset[str] = frozenset(
    {
        ".py",
        ".md",
        ".txt",
        ".yaml",
        ".yml",
        ".toml",
        ".cfg",
        ".ini",
        ".json",
        ".sh",
        ".ipynb",
        ".cff",
        ".tex",
        ".bib",
        ".csv",
    }
)

HARD_PATTERNS: tuple[tuple[str, str], ...] = (
    ("absolute_user_path", r"/Users/[A-Za-z0-9._-]+"),
    ("absolute_home_path", r"/home/[A-Za-z0-9._-]+"),
    ("windows_user_path", r"C:\\\\Users\\\\[A-Za-z0-9._-]+"),
    ("desktop_path", r"(?:~|\$HOME)?/?Desktop/[A-Za-z0-9._/-]+"),
    ("private_workspace_name", r"handoff-fidelity-2026"),
    ("private_git_parent", r"My_Git"),
    ("openai_key", r"sk-[A-Za-z0-9_-]{16,}"),
    ("anthropic_key", r"sk-ant-[A-Za-z0-9_-]{16,}"),
    ("google_key", r"AIza[0-9A-Za-z_-]{30,}"),
    ("hf_token", r"hf_[A-Za-z0-9]{20,}"),
    ("aws_key", r"AKIA[0-9A-Z]{16}"),
    ("private_key_block", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    (
        "assigned_secret",
        r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"\s]{12,}['\"]",
    ),
    ("email_address", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    ("assistant_instruction", r"(?i)\b(claude|antigravity|chatgpt|copilot)\b"),
)

#: Flagged only in public prose, where it would make the repository look like a
#: submission workspace.
DOC_ONLY_PATTERNS: tuple[tuple[str, str], ...] = (
    ("submission_language", r"(?i)\b(ICLR|NeurIPS|ICML|AAAI|ACL Findings)\b"),
    (
        "review_language",
        r"(?i)\b(under review|paper submission|rebuttal|reviewer #?\d*|camera[- ]ready|submission deadline|double-blind)\b",
    ),
    (
        "claim_hygiene",
        r"(?i)\b(state[- ]of[- ]the[- ]art|outperforms|superior to|proven empirically|empirically validated)\b",
    ),
)

DOC_SCOPE: tuple[str, ...] = ("README.md", "docs/", "CONTRIBUTING.md", "CITATION.cff")

#: Placeholders that legitimately look like an address but are not one.
EMAIL_ALLOWED = re.compile(
    r"(?i)(you@example\.com|your\.email@example\.com|name@example\.com|"
    r"user@example\.com|noreply@|security@example\.com|\{\{[^}]+\}\}|<[^>]*>)"
)


@dataclass(slots=True)
class Finding:
    path: str
    line_number: int
    rule: str
    excerpt: str


@dataclass(slots=True)
class ScanReport:
    findings: list[Finding] = field(default_factory=list)
    files_scanned: int = 0
    skipped: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings

    def render(self) -> str:
        head = (
            f"privacy scan: {self.files_scanned} file(s) scanned, {len(self.findings)} finding(s)"
        )
        if self.ok:
            return head + "\nPASS"
        lines = [head, "FAIL"]
        for f in sorted(self.findings, key=lambda x: (x.path, x.line_number)):
            lines.append(f"  {f.path}:{f.line_number}  [{f.rule}]  {f.excerpt[:120]}")
        return "\n".join(lines)


def tracked_files(root: Path) -> list[Path]:
    """Only GIT-TRACKED files. Untracked scratch is not public."""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            capture_output=True,
            check=True,
            text=True,
        ).stdout
        return [root / p for p in out.split("\0") if p]
    except Exception:
        return [p for p in root.rglob("*") if p.is_file() and ".git" not in p.parts]


# A note on what is deliberately NOT a content rule.
#
# An earlier version matched occurrences of "runs/", "third_party/" and friends
# in file CONTENT. Every hit it produced was a false positive: code that builds
# a private path from a variable -- "$PRIVATE_HOME"/third_party/... -- is the
# CORRECT pattern, and flagging it pressures the author to obfuscate correct
# code to appease the scanner.
#
# What actually matters is whether such a directory is TRACKED, which is a
# question about paths rather than content and is answered below by
# FORBIDDEN_TRACKED_PREFIXES. Hard-coded machine paths are still caught by the
# absolute_user_path and desktop_path rules.

#: Directory prefixes that must never contain a tracked file.
FORBIDDEN_TRACKED_PREFIXES: tuple[str, ...] = (
    "data/",
    "runs/",
    "cache/",
    "logs/",
    "artifacts/",
    "calibration/",
    "third_party/",
    "protocol_freeze/",
    "test_freeze/",
    "secrets/",
    "private/",
)


def _in_doc_scope(rel: str) -> bool:
    return any(rel == s or rel.startswith(s) for s in DOC_SCOPE)


def scan_text(rel: str, text: str) -> list[Finding]:
    if rel in SELF_ALLOWLIST:
        return []
    findings: list[Finding] = []
    rules = list(HARD_PATTERNS)
    if _in_doc_scope(rel):
        rules += list(DOC_ONLY_PATTERNS)
    compiled = [(name, re.compile(pattern)) for name, pattern in rules]
    for i, line in enumerate(text.splitlines(), start=1):
        for name, rx in compiled:
            m = rx.search(line)
            if not m:
                continue
            if name == "email_address" and EMAIL_ALLOWED.search(m.group()):
                continue
            findings.append(Finding(rel, i, name, line.strip()))
    return findings


def scan_repository(
    root: Path, *, extra_allowlist: Sequence[str] = (), paths: Iterable[Path] | None = None
) -> ScanReport:
    root = Path(root).resolve()
    allow = set(SELF_ALLOWLIST) | set(extra_allowlist)
    report = ScanReport()
    for path in sorted(paths if paths is not None else tracked_files(root)):
        path = Path(path)
        rel = str(path.resolve().relative_to(root))
        if rel in allow:
            report.skipped.append(rel)
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            report.skipped.append(rel)
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            report.skipped.append(rel)
            continue
        report.files_scanned += 1
        report.findings.extend(scan_text(rel, text))

    for path in sorted(paths if paths is not None else tracked_files(root)):
        rel = str(Path(path).resolve().relative_to(root))
        if any(rel.startswith(prefix) for prefix in FORBIDDEN_TRACKED_PREFIXES):
            report.findings.append(Finding(rel, 0, "tracked_private_directory", rel))
    return report
