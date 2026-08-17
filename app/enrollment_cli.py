"""Operator CLI for the physical steps of an ADMS enrollment session.

PromptID: ADMS-Frontend-WriteEnablement-001 / ADMS-ZEM560-TerminalAccount-Idempotency-Recovery-008

Emergency/fallback tooling only — the normal workflow is the browser-driven
create-terminal-account endpoint (dispatched over the DeviceCommandBus to the
live Collector). This CLI exists for the rare case where that path is
unavailable; it runs on ai-brain inside the listener container to perform the
operator-driven physical step while the Collector is paused.

Run inside the listener container (pyzk + DB env + device env present):

    python -m app.enrollment_cli status --enrollment-id 2
    python -m app.enrollment_cli create-terminal-account \
        --enrollment-id 2 --display-name "Somchai S." \
        --confirm-collector-paused

Subcommands:

  status                     Read-only enrollment state (safe anytime).
  create-terminal-account    Idempotent create/reconcile via the canonical
                             create_or_reconcile_terminal_account() — safe
                             to re-run (e.g. after an uncertain outcome);
                             never calls set_user() a second time if the
                             account already exists and matches, and never
                             overwrites a conflicting account. Requires
                             --confirm-collector-paused (the Collector holds
                             the terminal's single connection and MUST be
                             stopped before this runs).

The CLI never auto-connects and never falls back to a second connection: the
device connection is created explicitly, passed to the canonical function,
and torn down afterwards. No fingerprint data is read or written.
"""

import argparse
import sys
from typing import Any, Dict, Optional

from app.config import Config
from app.enrollment import (
    EnrollmentError,
    TerminalAccountConflict,
    TerminalAccountUnconfirmed,
    create_or_reconcile_terminal_account,
    get_enrollment,
)


def _print_enrollment(label: str, e: Dict[str, Any]) -> None:
    print("=== %s ===" % label)
    print("enrollment_id: %s" % e.get("enrollment_id"))
    print("status: %s" % e.get("status"))
    print("employee_id: %s" % e.get("employee_id"))
    print("device_id: %s" % e.get("device_id"))
    print("reserved_device_user_id: %s" % e.get("reserved_device_user_id"))
    print("operator: %s" % e.get("reserved_by") or e.get("created_by"))
    print("created_at: %s" % e.get("created_at"))
    print("terminal_created_at: %s" % e.get("terminal_created_at"))


def _connect_device(cfg: Config):
    """Explicitly create and connect a pyzk connection (never implicit)."""
    try:
        from zk import ZK  # pyzk is a listener-container dependency
    except ImportError as e:  # pragma: no cover - env check
        raise SystemExit(
            "ERROR: pyzk not available — run this inside the listener "
            "container (docker exec adms_zkteco_listener ...). (%s)" % e
        )
    zk = ZK(
        cfg.device_ip,
        port=cfg.device_port,
        timeout=cfg.device_timeout,
        password=cfg.device_password,
    )
    conn = zk.connect()
    if conn is None:
        raise SystemExit(
            "ERROR: could not connect to terminal %s:%s" % (cfg.device_ip, cfg.device_port)
        )
    return conn


def cmd_status(args: argparse.Namespace) -> int:
    cfg = Config.from_env()
    try:
        e = get_enrollment(cfg, args.enrollment_id)
    except EnrollmentError as err:
        print("ERROR: %s" % err, file=sys.stderr)
        return 1
    _print_enrollment("Enrollment %s" % args.enrollment_id, e)
    return 0


def cmd_create_terminal_account(args: argparse.Namespace) -> int:
    if not args.confirm_collector_paused:
        print(
            "ERROR: refusing to run without --confirm-collector-paused.\n"
            "The running Collector holds the terminal's single ZK connection.\n"
            "Stop the Collector first (docker compose stop listener), run this,\n"
            "then start it again (docker compose start listener).",
            file=sys.stderr,
        )
        return 1
    cfg = Config.from_env()
    try:
        e = get_enrollment(cfg, args.enrollment_id)
    except EnrollmentError as err:
        print("ERROR: %s" % err, file=sys.stderr)
        return 1
    _print_enrollment("Pre-write state", e)

    conn: Optional[Any] = None
    try:
        conn = _connect_device(cfg)
        result = create_or_reconcile_terminal_account(
            cfg, args.enrollment_id, args.display_name, conn
        )
    except TerminalAccountConflict as err:
        print("CONFLICT: %s" % err, file=sys.stderr)
        print(
            "The terminal ID exists but does not match this enrollment's "
            "expected identity. NOT overwritten, NOT deleted. Manual review "
            "required before proceeding.",
            file=sys.stderr,
        )
        return 1
    except TerminalAccountUnconfirmed as err:
        print("UNCONFIRMED: %s" % err, file=sys.stderr)
        print(
            "The account could not be confirmed present after bounded "
            "read-back. Enrollment state is unchanged — re-running this "
            "same command is safe.",
            file=sys.stderr,
        )
        return 1
    except EnrollmentError as err:
        print("ERROR: %s" % err, file=sys.stderr)
        return 1
    finally:
        if conn is not None:
            try:
                conn.disconnect()
            except Exception:  # pragma: no cover - best-effort teardown
                pass

    print("OK: terminal account %s." % ("reconciled" if result.get("reconciled") else "created"))
    print("  enrollment_id: %s" % result.get("enrollment_id"))
    print("  status: %s" % result.get("status"))
    print("  terminal_id: %s" % result.get("terminal_id"))
    print("  device_uid: %s" % result.get("device_uid"))
    print("NEXT: restart the Collector, then enroll the fingerprint at the "
          "terminal UI and use the console to confirm.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.enrollment_cli",
        description="Operator CLI for physical ADMS enrollment steps.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="read-only enrollment state")
    p_status.add_argument("--enrollment-id", type=int, required=True)
    p_status.set_defaults(func=cmd_status)

    p_create = sub.add_parser(
        "create-terminal-account",
        help="physical set_user() for a RESERVED enrollment (Collector must be paused)",
    )
    p_create.add_argument("--enrollment-id", type=int, required=True)
    p_create.add_argument("--display-name", required=True)
    p_create.add_argument(
        "--confirm-collector-paused",
        action="store_true",
        help="confirm the Collector is stopped (it holds the single ZK connection)",
    )
    p_create.set_defaults(func=cmd_create_terminal_account)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
