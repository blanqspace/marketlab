from __future__ import annotations

"""Number-based, stdin-only control menu.

- No hotkeys, no screen=True usage.
- Slim main menu; pending orders are listed lazily for actions 4/5.
"""

import sys
import warnings
from typing import Optional

from .ipc import bus
from .orders import store as orders
from .settings import get_settings
from .bootstrap.env import load_env

# Marked for deprecation in favour of the Textual TUI dashboard/CLI flows.
warnings.warn(
    "marketlab.control_menu is deprecated; prefer the Textual dashboard or CLI commands.",
    DeprecationWarning,
    stacklevel=2,
)

# Ensure .env is loaded early (no-op if already cached)
try:
    load_env(mirror=True)
except Exception:
    pass


def _ask_yes_no(prompt: str) -> bool:
    """Ask a yes/no question on stdin and return True if 'y'."""
    while True:
        sys.stdout.write(f"{prompt} [y/n]: ")
        sys.stdout.flush()
        ans = sys.stdin.readline().strip().lower()
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False


def _ask_id(prompt: str) -> str:
    """Ask for an input; reject empty input."""
    while True:
        sys.stdout.write(f"{prompt}: ")
        sys.stdout.flush()
        val = sys.stdin.readline().strip()
        if val:
            return val
        sys.stdout.write("Eingabe darf nicht leer sein.\n")
        sys.stdout.flush()


def _print_menu(last_token: str | None = None) -> None:
    last = last_token or "-"
    sys.stdout.write(
        "\nMarketLab Control Menu\n"
        f"Last: {last}\n"
        "  1) Pause\n"
        "  2) Resume\n"
        "  3) Stop\n"
        "  4) Confirm\n"
        "  5) Reject\n"
        "  6) Paper\n"
        "  7) Live\n"
        "  9) Exit\n"
    )
    sys.stdout.flush()


def _parse_selector(token_or_n: str) -> str | int:
    token_or_n = (token_or_n or "").strip()
    if not token_or_n:
        raise ValueError("ung ltiger Selector")
    if token_or_n.isdigit():
        return int(token_or_n)
    return token_or_n


def _enqueue_and_print(cmd: str, args: dict) -> None:
    bus.enqueue(cmd, args, source="cli")
    token_out = args.get("token") or "?"
    sys.stdout.write(f"OK: {cmd} -> {token_out}\n")
    sys.stdout.flush()


def _print_pending_page(pending: list[dict], page: int, page_size: int = 10) -> None:
    total = len(pending)
    if total == 0:
        sys.stdout.write("Keine Pending-Orders.\n")
        sys.stdout.flush()
        return
    start = page * page_size
    end = min(start + page_size, total)
    sys.stdout.write(f"Pending Orders {start+1}-{end} von {total}\n")
    for i, r in enumerate(pending[start:end], start=1):
        sys.stdout.write(
            f"  {i}) {r['symbol']} {r['side']} {r['qty']} {r['type']} [{r.get('token','-')}]\n"
        )
    sys.stdout.write("Eingabe: Zahl 1-10 | Token | n/p | q\n")
    sys.stdout.flush()


def _lazy_select_and_act(kind: str) -> None:
    """Interactive, paginated pending selection for confirm/reject.

    kind: 'confirm' | 'reject'
    """
    pending = orders.get_pending(limit=20)
    if not pending:
        sys.stdout.write("Keine Pending-Orders.\n"); sys.stdout.flush(); return
    page = 0
    page_size = 10
    while True:
        _print_pending_page(pending, page, page_size)
        sys.stdout.write("> "); sys.stdout.flush()
        sel = (sys.stdin.readline() or "").strip()
        if not sel:
            continue
        low = sel.lower()
        if low == "q":
            return
        if low == "n":
            if (page + 1) * page_size < len(pending):
                page += 1
            continue
        if low == "p":
            if page > 0:
                page -= 1
            continue
        # token or number
        chosen_token: str | None = None
        if sel.isdigit():
            n = int(sel)
            if 1 <= n <= min(page_size, len(pending) - page * page_size):
                rec = pending[page * page_size + (n - 1)]
                chosen_token = rec.get("token")
        else:
            chosen_token = sel
        if not chosen_token:
            sys.stdout.write("Ung ltige Auswahl.\n"); sys.stdout.flush(); continue
        if kind == "confirm":
            _enqueue_and_print("orders.confirm", {"token": chosen_token})
            return
        else:
            if _ask_yes_no(f"Reject {chosen_token}?"):
                _enqueue_and_print("orders.reject", {"token": chosen_token})
                return


def run_menu() -> None:
    """Run the prompt-based control menu (stdin only)."""
    last_action: Optional[tuple[str, str | int]] = None
    while True:
        last_token = None
        if last_action and isinstance(last_action[1], (str, int)):
            try:
                rec = orders.resolve_order(last_action[1])
                last_token = rec.get("token")
            except Exception:
                last_token = None
        _print_menu(last_token)
        sys.stdout.write("Auswahl: ")
        sys.stdout.flush()
        raw = sys.stdin.readline().strip()
        if not raw and last_action:
            # Repeat last action using token if possible
            try:
                rec = orders.resolve_order(last_action[1])
                tok = rec.get("token")
                _enqueue_and_print(last_action[0], {"token": tok} if tok else {})
            except Exception:
                pass
            continue
        parts = raw.split()
        choice = parts[0] if parts else ""
        arg = parts[1] if len(parts) > 1 else None
        if choice == "1":
            _enqueue_and_print("state.pause", {})
        elif choice == "2":
            _enqueue_and_print("state.resume", {})
        elif choice == "3":
            if _ask_yes_no("Stop ausf hren?"):
                _enqueue_and_print("state.stop", {})
        elif choice == "4":
            if arg:
                try:
                    selector = _parse_selector(arg)
                except Exception:
                    sys.stdout.write("Fehler: ung ltiger Selector\n"); sys.stdout.flush(); continue
                if isinstance(selector, int):
                    pend = orders.get_pending(limit=max(selector, 20))
                    if 1 <= selector <= len(pend):
                        tok = pend[selector - 1].get("token")
                        _enqueue_and_print("orders.confirm", {"token": tok})
                        last_action = ("orders.confirm", selector)
                    else:
                        sys.stdout.write("Fehler: ung ltiger Selector\n"); sys.stdout.flush()
                else:
                    _enqueue_and_print("orders.confirm", {"token": selector})
                    last_action = ("orders.confirm", selector)
            else:
                _lazy_select_and_act("confirm")
        elif choice == "5":
            if arg:
                try:
                    selector = _parse_selector(arg)
                except Exception:
                    sys.stdout.write("Fehler: ung ltiger Selector\n"); sys.stdout.flush(); continue
                if isinstance(selector, int):
                    pend = orders.get_pending(limit=max(selector, 20))
                    if 1 <= selector <= len(pend):
                        tok = pend[selector - 1].get("token")
                        if _ask_yes_no(f"Reject {tok}?"):
                            _enqueue_and_print("orders.reject", {"token": tok})
                            last_action = ("orders.reject", selector)
                    else:
                        sys.stdout.write("Fehler: ung ltiger Selector\n"); sys.stdout.flush()
                else:
                    if _ask_yes_no(f"Reject {selector}?"):
                        _enqueue_and_print("orders.reject", {"token": selector})
                        last_action = ("orders.reject", selector)
            else:
                _lazy_select_and_act("reject")
        elif choice == "6":
            _enqueue_and_print(
                "mode.switch",
                {"target": "paper", "args": {"symbols": ["AAPL"], "timeframe": "1m"}},
            )
        elif choice == "7":
            _enqueue_and_print(
                "mode.switch",
                {"target": "live", "args": {"symbols": ["AAPL"], "timeframe": "1m"}},
            )
        elif choice == "9":
            sys.stdout.write("Beenden...\n"); sys.stdout.flush(); return
        else:
            sys.stdout.write("Ung ltige Auswahl.\n")
            sys.stdout.flush()
