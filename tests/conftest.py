"""Shared pytest configuration.

Adds ``scripts/`` to ``sys.path`` so the ``lib`` package can be imported
the same way the scripts do at runtime.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
