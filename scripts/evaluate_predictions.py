"""Thin source-checkout wrapper for ``plategauge evaluate``."""

from __future__ import annotations

import sys

from plategauge.cli import main

raise SystemExit(main(["evaluate", *sys.argv[1:]]))
