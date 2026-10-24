"""Allow ``python -m claude_select``."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
