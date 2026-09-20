"""Thin source-checkout wrapper for ``plategauge audit-data``."""

from __future__ import annotations

import sys

from plategauge.cli import main

raise SystemExit(main(["audit-data", *sys.argv[1:]]))
