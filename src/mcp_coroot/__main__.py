"""Allow ``python -m mcp_coroot``."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
