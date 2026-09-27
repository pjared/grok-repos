"""python -m suit_o"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from suit_o.app import SuitOApp
from suit_o.config import DEFAULT_CONFIG_PATH, ConfigError, load_config

logger = logging.getLogger("suit_o")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="suit-o",
        description="Local Counter-Strike 2 companion. Speaks into your headset from GSI.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to config.yaml (default: suit-o-cs2/config.yaml)",
    )
    parser.add_argument("--mute", action="store_true", help="Start muted")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        config = load_config(args.config)
    except (ConfigError, OSError, ValueError) as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2
    if args.mute:
        config.mute = True
    for warning in config.warnings:
        logger.warning("%s", warning)

    try:
        app = SuitOApp(config)
    except NotImplementedError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        app.start(console=True)
    except OSError as exc:
        print(
            f"Could not listen on {config.server.host}:{config.server.port}: {exc}\n"
            "Another program is using that port, or the address is not available.",
            file=sys.stderr,
        )
        return 1

    host, port = app.server_address
    logger.info("GSI endpoint ready at http://%s:%s/", host, port)
    logger.info(
        "Copy gamestate_integration_suito.cfg into the CS2 cfg folder and "
        "restart Counter-Strike 2. server.token must match the cfg auth token."
    )
    if not sys.stdin.isatty():
        logger.info("Mute from another terminal: POST http://%s:%s/mute", host, port)
        logger.info("Status: GET http://%s:%s/status", host, port)
    try:
        app.wait_forever()
    except KeyboardInterrupt:
        logger.info("Stopping.")
    finally:
        app.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
