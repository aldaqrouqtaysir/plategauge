"""Current entry points agree with one release table; historical sections stay free."""

from __future__ import annotations

import hashlib
import json
import re
import unittest
from pathlib import Path


class CurrentReleaseDocumentationTests(unittest.TestCase):
    def test_current_entry_points_match_the_published_profile_and_inventory(self) -> None:
        root = Path(__file__).resolve().parents[2]
        current = (root / "docs/CURRENT_RELEASE.md").read_text(encoding="utf-8")
        section = current.split("## Current identities and observed checks\n", 1)[1].split("\n## ", 1)[0]
        tag_match = re.search(r"Published prerelease \| \[(camera-experimental-r[1-9][0-9]*)\]", section)
        self.assertIsNotNone(tag_match)
        assert tag_match is not None
        tag = tag_match.group(1)
        folder = "camera" if tag.endswith("-r1") else tag.replace("camera-experimental-", "camera-")
        raw = (root / "release" / folder / "inventory.json").read_bytes()
        inventory = json.loads(raw)
        self.assertIn(inventory["appSourceCommit"], section)
        self.assertIn(hashlib.sha256(raw).hexdigest(), section)
        self.assertIn(f'[{len(inventory["files"])}-file inventory]', section)
        self.assertIn(f"../release/{folder}/inventory.json", section)
        expected_link = f"https://github.com/aldaqrouqtaysir/plategauge/releases/tag/{tag}"
        for name in ("README.md", "SECURITY.md"):
            text = (root / name).read_text(encoding="utf-8")
            self.assertIn(expected_link, text, name)
            # These are current entry points, unlike the explicit historical records.
            links = re.findall(r"releases/tag/(camera-experimental-r[0-9]+)", text)
            self.assertTrue(links and all(link == tag for link in links), name)
        quickstart = (root / "docs/REVIEWER_QUICKSTART.md").read_text(encoding="utf-8")
        self.assertIn(f"The live profile is `{tag}`", quickstart)
        build = (root / "docs/CAMERA_CANDIDATE_BUILD.md").read_text(encoding="utf-8")
        self.assertTrue(build.splitlines()[2].startswith(f"`{tag}` was published"))
        monitoring = (root / "docs/MONITORING_AND_FAILURES.md").read_text(encoding="utf-8")
        self.assertIn(f"The active profile is `{tag}`", monitoring.split("## Historical", 1)[0])


if __name__ == "__main__":
    unittest.main()
