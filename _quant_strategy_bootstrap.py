"""Allow existing Freqtrade file-based entry points to use the src package."""

import sys
from pathlib import Path

source = str(Path(__file__).resolve().parent / "src")
if source not in sys.path:
    sys.path.insert(0, source)
