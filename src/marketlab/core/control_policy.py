from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ControlPolicy:
    risk: str
    approvals_required: int
    approval_window_sec: int


DEFAULT_POLICY = ControlPolicy(risk="LOW", approvals_required=1, approval_window_sec=30)

# Central risk matrix for command bus operations.
_POLICY_TABLE: Mapping[str, ControlPolicy] = {
    "state.pause": ControlPolicy(risk="LOW", approvals_required=1, approval_window_sec=30),
    "state.resume": ControlPolicy(risk="LOW", approvals_required=1, approval_window_sec=30),
    "state.stop": ControlPolicy(risk="LOW", approvals_required=1, approval_window_sec=30),
    "stop.now": ControlPolicy(risk="CRITICAL", approvals_required=1, approval_window_sec=5),
    "orders.confirm": ControlPolicy(risk="HIGH", approvals_required=2, approval_window_sec=90),
    "orders.reject": ControlPolicy(risk="HIGH", approvals_required=2, approval_window_sec=90),
    "orders.cancel": ControlPolicy(risk="HIGH", approvals_required=2, approval_window_sec=90),
    "orders.confirm_all": ControlPolicy(risk="HIGH", approvals_required=2, approval_window_sec=90),
    "mode.switch": ControlPolicy(risk="LOW", approvals_required=1, approval_window_sec=30),
    "live.cancel": ControlPolicy(risk="HIGH", approvals_required=2, approval_window_sec=90),
    "portfolio.adjust": ControlPolicy(risk="HIGH", approvals_required=2, approval_window_sec=120),
}


def policy_for(cmd: str) -> ControlPolicy:
    """Return control policy for command, falling back to default."""
    return _POLICY_TABLE.get(cmd, DEFAULT_POLICY)


def risk_of_command(cmd: str) -> str:
    return policy_for(cmd).risk


def approvals_required(cmd: str) -> int:
    return policy_for(cmd).approvals_required


def approval_window(cmd: str) -> int:
    return policy_for(cmd).approval_window_sec


def command_target(cmd: str, args: Mapping[str, Any] | None = None) -> str:
    payload = args or {}
    if cmd.startswith("orders."):
        for key in ("token", "id", "selector"):
            if key in payload and payload.get(key):
                return str(payload.get(key))
    if cmd == "mode.switch":
        return str(payload.get("target", "unknown"))
    if "id" in payload and payload.get("id"):
        return str(payload.get("id"))
    return cmd


__all__ = [
    "ControlPolicy",
    "DEFAULT_POLICY",
    "policy_for",
    "risk_of_command",
    "approvals_required",
    "approval_window",
    "command_target",
]
