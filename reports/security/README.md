# Dependency scan snapshot

Refreshed locally on 20 September 2026 from the locked release-candidate
environments. These files are time-sensitive Gate D candidate evidence, not a
substitute for the fresh release-CI scans.

- `python-audit.json`: 76 resolved entries, zero known vulnerabilities among 75
  auditable entries; local editable `plategauge` 1.0.0 is the single documented
  unaudited entry because it is not published on PyPI.
- `python-licenses.json`: installed Python dependency/license inventory.
- `node-production-audit.json`: production JavaScript dependency audit.
- `node-full-audit.json`: production and development JavaScript dependency
  audit.
- `node-production-licenses.json`: production JavaScript license inventory;
  local absolute installation paths were removed from the saved copy.

The audit results are time-sensitive. The release workflow regenerates and
validates its own evidence rather than trusting these files.
