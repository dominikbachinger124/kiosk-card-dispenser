"""Command-line entry point for the kiosk.

Only ``--check-config`` is implemented so far. It validates the configuration
and touches no hardware. Output never contains device paths, admin UIDs or
PIN hashes.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from kiosk.config import load_config
from kiosk.domain.errors import ConfigError

DEFAULT_CONFIG_PATH = Path("config.toml")


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
    args = parser.parse_args(argv)

    if not args.check_config:
        parser.print_help(sys.stderr)
        return 1

    try:
        load_config(args.config)
    except ConfigError:
        # Only the stable code is printed. The message may name a path or key
        # that is operator-specific, so it stays out of the output.
        print("CONFIG_INVALID", file=sys.stderr)
        return 2
    print("config ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
