"""Command-line entry point for the kiosk.

``--check-config`` validates the configuration and touches no hardware.
Without it, the kiosk bootstraps: configuration, salt, database and services.
No serial port is opened at startup. Output never contains device paths,
admin UIDs or PIN hashes.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from kiosk.bootstrap import build_app
from kiosk.config import load_config
from kiosk.domain.errors import ConfigError
from kiosk.env_file import load_env_file
from kiosk.logging_setup import configure_logging

DEFAULT_CONFIG_PATH = Path("config.toml")
DEFAULT_LOG_DIR = Path("~/.local/state/kiosk/logs")
DEFAULT_ENV_PATH = Path(".env")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface.

    Args:
        argv: Arguments without the program name. Defaults to ``sys.argv``.

    Returns:
        Process exit code: 0 on success, 2 on invalid configuration.
    """
    parser = argparse.ArgumentParser(prog="kiosk")
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="validate the configuration and exit; no hardware is accessed",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="path to the TOML configuration file",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="load the main window offscreen and exit; no event loop, no hardware",
    )
    parser.add_argument(
        "--bootstrap-only",
        action="store_true",
        help="run the bootstrap and exit without starting the window (diagnosis)",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="database file (default: ~/.local/share/kiosk/kiosk.db)",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=DEFAULT_LOG_DIR,
        help="directory for kiosk.log (default: ~/.local/state/kiosk/logs)",
    )
    args = parser.parse_args(argv)

    if not args.check_config:
        # Logging first, so the bootstrap and the flows write JSON lines.
        configure_logging(args.log_dir.expanduser())

    try:
        if args.check_config:
            load_config(args.config)
            print("config ok")
            return 0
        # Local secrets (salt) come from .env; an explicit shell value wins.
        load_env_file(DEFAULT_ENV_PATH, os.environ)
        app = build_app(args.config, db_path=args.db)
    except (ConfigError, ValueError):
        # Only the stable code is printed. The message may name a path or key
        # that is operator-specific, so it stays out of the output.
        print("CONFIG_INVALID", file=sys.stderr)
        return 2
    if args.smoke:
        from kiosk.gui.app import run_smoke

        run_smoke(app)
        print("smoke ok")
        return 0
    if args.bootstrap_only:
        print("bootstrap ok")
        return 0
    from kiosk.gui.app import run_app

    return run_app(app)


if __name__ == "__main__":
    raise SystemExit(main())
