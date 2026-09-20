from __future__ import annotations

import unittest
from pathlib import Path

from plategauge.gate_d_audit import audit_gate_d_candidate


class GateDAuditTests(unittest.TestCase):
    @property
    def repo_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    def test_local_candidate_is_technically_clean_but_not_release_authorized(self) -> None:
        report = audit_gate_d_candidate(self.repo_root)
        self.assertEqual(report["technicalStatus"], "passed")
        self.assertEqual(report["releaseReadiness"], "blocked_pending_gate_d_actions")
        self.assertEqual(report["failedChecks"], [])
        self.assertIn("gate_d_approval", report["pendingChecks"])
        self.assertIn("source_commit", report["pendingChecks"])
        by_id = {check["id"]: check for check in report["checks"]}
        self.assertEqual(by_id["static_bundle_allowlist"]["status"], "pass")
        self.assertEqual(by_id["web_benchmark_evidence_binding"]["status"], "pass")
        self.assertEqual(by_id["web_benchmark_evidence_binding"]["evidence"]["exampleCount"], 10)
        self.assertEqual(by_id["raw_data_boundary"]["status"], "pass")
        self.assertTrue(by_id["raw_data_boundary"]["evidence"]["localRawDirectoryIgnored"])
        self.assertEqual(by_id["secret_and_host_path_scan"]["status"], "pass")
        self.assertEqual(by_id["public_smoke_fail_closed"]["status"], "pass")
        self.assertEqual(by_id["candidate_version_consistency"]["status"], "pass")
        self.assertNotIn("final_manifest_version", report["pendingChecks"])


if __name__ == "__main__":
    unittest.main()
