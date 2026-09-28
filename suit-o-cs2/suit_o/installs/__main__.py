"""``python -m suit_o.installs prefetch <part>`` downloads that part's models.

The Installations window runs this in a separate, hidden Python after pip, so
freshly installed packages import cleanly.
"""

from __future__ import annotations

import sys

from suit_o.installs.components import InstallError, prefetch


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2 or args[0] != "prefetch":
        print("usage: python -m suit_o.installs prefetch <chat|voice|clips>", file=sys.stderr)
        return 2
    try:
        prefetch(args[1])
    except InstallError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Could not download models for {args[1]}. {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
