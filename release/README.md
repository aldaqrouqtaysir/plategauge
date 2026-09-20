# Gate D approval record

This directory intentionally contains **no approval artifact** during
development. Public deployment remains blocked until the applicant has reviewed
the frozen evidence and explicitly approved Gate D.

After that real approval, record it as `release/gate-d-approval.json`. Schema
version 1 has exactly these fields:

```json
{
  "schemaVersion": 1,
  "gate": "D",
  "decision": "approved",
  "approvedBy": "Taysir Al Daqrouq",
  "approvedAt": "ISO-8601 timestamp with UTC offset",
  "releaseTag": "v1.0.0",
  "sourceCommitSha": "40-character lowercase SHA of the frozen source commit",
  "evidence": {
    "modelSha256": "64 lowercase hexadecimal characters",
    "releaseManifestSha256": "64 lowercase hexadecimal characters",
    "resultsSha256": "64 lowercase hexadecimal characters",
    "claimEvidenceSha256": "64 lowercase hexadecimal characters"
  }
}
```

The hashes bind the approval to these fixed paths:

- `web/public/models/plategauge.onnx`
- `web/public/models/release.json`
- `reports/results.json`
- `docs/CLAIM_EVIDENCE_MAP.csv`

This is checksum binding, not cryptographic signing. The repository does not
currently create or verify a digital signature for this JSON record or the
listed release artifacts.

`scripts/verify_release_gate.py` rejects missing, pending, stale, malformed, or
mismatched evidence. It also loads and smoke-runs the exact ONNX artifact and
requires `reports/results.json` to declare `schemaVersion: 1` and `frozen: true`.
It never creates approval and must not be used to infer one.

The release tag must point to a single approval commit immediately after
`sourceCommitSha`. That approval commit may change only
`release/gate-d-approval.json`; this avoids an impossible self-referential commit
hash while binding the approval to the complete frozen source tree.
