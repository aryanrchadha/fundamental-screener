"""`python -m dashboard` — launch the GUI and open it in a browser."""

import sys

from dashboard.app import main

main(sys.argv[1:] if "--open" in sys.argv[1:] else [*sys.argv[1:], "--open"])
