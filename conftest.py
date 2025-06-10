"""Ensure the repository root is importable when tests run.

Lets ``from localrag... import ...`` work whether tests are run via
``python -m pytest`` or the bare ``pytest`` console script (which does not add
the current directory to ``sys.path``).
"""

import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
