"""Policy engine selection.

Prefers OPA when the binary and bundle are present; otherwise the local mirror.
Both are fail-closed, and a DENY from either is final -- the engines are never
consulted until one of them allows.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .decisions import PolicyDecision, PolicyInput, evaluate_local

DEFAULT_POLICY_DIR = Path("policies/rego")
OPA_QUERY = "data.handoff.lifecycle.decision"


def opa_available() -> bool:
    return shutil.which("opa") is not None


@dataclass(slots=True)
class PolicyEngine:
    policy_dir: Path = DEFAULT_POLICY_DIR
    prefer_opa: bool = True

    def describe(self) -> dict[str, object]:
        return {
            "opa_binary_available": opa_available(),
            "policy_dir": str(self.policy_dir),
            "policy_dir_exists": Path(self.policy_dir).exists(),
            "active_engine": "opa"
            if (self.prefer_opa and opa_available() and Path(self.policy_dir).exists())
            else "local-mirror",
        }

    def evaluate(self, inp: PolicyInput) -> PolicyDecision:
        local = evaluate_local(inp)
        if not (self.prefer_opa and opa_available() and Path(self.policy_dir).exists()):
            return local
        try:
            opa = self._evaluate_opa(inp)
        except Exception:
            # A broken policy engine must never widen permissions.
            return local
        if opa.allow != local.allow:
            # Disagreement is itself a defect. Take the stricter answer and say so.
            return PolicyDecision(
                allow=False,
                reasons=(
                    "OPA and the local mirror disagree; denying and reporting. "
                    f"opa={opa.allow} local={local.allow}",
                    *opa.reasons,
                    *local.reasons,
                ),
                engine="disagreement",
            )
        return opa

    def _evaluate_opa(self, inp: PolicyInput) -> PolicyDecision:
        proc = subprocess.run(
            [
                "opa",
                "eval",
                "--format",
                "json",
                "--data",
                str(self.policy_dir),
                "--stdin-input",
                OPA_QUERY,
            ],
            input=json.dumps(inp.to_dict()),
            capture_output=True,
            text=True,
            check=True,
            timeout=20,
        )
        payload = json.loads(proc.stdout)
        value = payload["result"][0]["expressions"][0]["value"]
        return PolicyDecision(
            allow=bool(value.get("allow", False)),
            reasons=tuple(value.get("reasons", ("no reason given",))),
            engine="opa",
        )
