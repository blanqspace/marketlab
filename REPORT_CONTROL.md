# MarketLab Control Hardening

## Overview

This document summarizes the current hardening of the MarketLab control plane (CLI, Telegram, supervisor) covering risk policies, dual-control, kill-switch integration, telemetry, and test coverage.

## Command Risk Matrix

| Command | Risk | Approvals | Notes |
| --- | --- | --- | --- |
| `state.pause`, `state.resume`, `state.stop` | LOW | 1 | Operational toggles |
| `mode.switch` | LOW | 1 | Paper/Live mode switch |
| `orders.confirm`, `orders.reject`, `orders.confirm_all`, `live.cancel`, `orders.cancel` | HIGH | 2 (distinct sources) | Requires Telegram + CLI (or other distinct sources) approvals within 90s |
| `stop.now` | CRITICAL | 1 | Kill-switch: immediate pause + cancels pending orders |

## Dual-Control & Approvals

- Approvals persist in the new `approvals` table with metadata (risk, required approvals, timestamps, sources).
- Worker enforces approvals via policy defined in `core.control_policy`; TTL enforced via the `approval_window` per command.
- Events emitted for lifecycle: `approval.pending`, `approval.fulfilled`, `approval.expired` plus legacy `orders.confirm.pending/expired`.
- KPIs (`approvals_pending`, `approvals_age_max`) derive from the approvals table for dashboards.

## Telegram Auth & Safety

- Allowlist enforced via settings (`TG_ALLOWLIST`).
- Optional PIN (`TG_CMD_PIN`) protects HIGH/CRITICAL commands. Users must authenticate with `/pin <PIN>`; session valid for 60s.
- Per-user rate limit (`TG_RATE_LIMIT_PER_MIN`, default 10/min). Excess commands receive guidance toast + chat message.
- Callback/text actions mapped to policy-aware commands; helpers ensure consistent request IDs and metadata.
- `tg_diag` supports `getme`, `chatinfo`, `sendtest -v`, `updates`, `ids`.

## Kill-Switch & Circuit Breaker

- `stop.now` command (CLI `marketlab stop-now`, control menu option 3, Telegram button `/stop`) pauses the system and marks pending/telegram-confirmed orders as `CANCELED`. Emits `stop.now` and sets `breaker.state = killswitch`.
- Circuit breaker monitors worker exceptions (`5` errors within `60s` by default). On trip:
  - worker forces pause, sets `breaker.state = tripped`, emits `breaker.tripped`.
  - manual `state.resume` resets breaker (`breaker.reset`, state to `ok`).

## Observability

- JSON logging formatter enriches records with `src`, `actor_id`, `cmd_id` when available.
- Status KPIs now include `approvals_pending`, `approvals_age_max`, and `breaker_state` for dashboard panels.
- `scripts/env_check.py` reports PIN presence and rate-limit configuration without leaking secrets.
- `make e2e` target exercises pause/resume/stop flows against an isolated DB.

## Runbook Highlights

1. **Dual approvals pending**: check dashboard approvals panel; if aged > window, instruct second approver or issue `/pin` if required.
2. **Kill-switch**: invoke `marketlab stop-now` or Telegram `/stop`; confirm `stop.now` event; follow up by reviewing canceled order list.
3. **Breaker tripped**: investigate `breaker.tripped` event, inspect recent `command_error` logs; once mitigated run `marketlab ctl enqueue --cmd state.resume` (or CLI `stop-now` followed by resume) to reset breaker state.
4. **Rate-limit hits**: notify operators; adjust `TG_RATE_LIMIT_PER_MIN` via `.env` if legitimately required.

## Test Matrix

| Test | Coverage |
| --- | --- |
| `tests/test_bus_idempotency_ttl.py` | Request-ID dedupe & TTL expiry audit |
| `tests/test_two_man_rule_flow.py` | Dual-control pending → fulfilled across sources |
| `tests/test_telegram_auth_rate_pin.py` | PIN/rate helpers, action mapping |
| `tests/test_killswitch_breaker.py` | Kill-switch cancels + breaker trip/reset |
| Existing `tests/test_worker_*` | State change, event emission regressions |
| `make e2e` | Pause → Resume → Stop.Now smoke validation |

