"""Thin source-checkout wrapper for ``plategauge build-manifest``."""

from __future__ import annotations

import sys

from plategauge.cli import main

raise SystemExit(main(["build-manifest", *sys.argv[1:]]))
