"""Finding / severity data model shared by every check module."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class Severity(enum.IntEnum):
    INFO = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

    @property
    def label(self) -> str:
        return self.name

    @classmethod
    def parse(cls, text: str) -> "Severity":
        try:
            return cls[text.strip().upper()]
        except KeyError as exc:  # pragma: no cover - argparse guards this
            raise ValueError(f"unknown severity {text!r}") from exc


# Console / markdown colour per severity (rich markup names).
SEV_COLOUR = {
    Severity.CRITICAL: "bold white on red",
    Severity.HIGH: "bold red",
    Severity.MEDIUM: "yellow",
    Severity.LOW: "cyan",
    Severity.INFO: "dim",
}


@dataclass
class Finding:
    code: str                 # stable slug, e.g. "rls.permissive_policy"
    severity: Severity
    title: str                # one line, specific
    obj: str                  # the object it is about: "public.students", "storage:Procksi", "auth"
    detail: str               # what is wrong and why it matters
    remediation: str          # concrete fix
    category: str = "misc"    # rls | grants | functions | storage | auth | jwt | probe | exposure
    evidence: Any = None      # dict / str shown verbatim in the report
    confirmed: bool = False   # True when a live probe proved it (not just config inference)

    def sort_key(self) -> tuple:
        return (-int(self.severity), self.category, self.obj, self.code)


@dataclass
class AuditReport:
    findings: list[Finding] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def add(self, f: Finding) -> None:
        self.findings.append(f)

    def extend(self, fs: list[Finding]) -> None:
        self.findings.extend(fs)

    def sorted(self) -> list[Finding]:
        return sorted(self.findings, key=lambda f: f.sort_key())

    def counts(self) -> dict[Severity, int]:
        out = {s: 0 for s in Severity}
        for f in self.findings:
            out[f.severity] += 1
        return out

    def worst(self) -> Severity:
        return max((f.severity for f in self.findings), default=Severity.INFO)
