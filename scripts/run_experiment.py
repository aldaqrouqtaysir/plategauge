"""Thin source-checkout wrapper for the guarded experiment entry point."""

from __future__ import annotations

import sys

from plategauge.cli import main

raise SystemExit(main(["run-experiment", *sys.argv[1:]]))
