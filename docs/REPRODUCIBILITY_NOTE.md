# Cross-platform reproducibility note

PlateGauge v1 preserves the frozen model, predictions, metrics, and scientific
decisions from source-freeze commit
`ef171111459afd1ba5a73ee7291041b32fcbc376`. A later pre-release audit found
that the source-freeze tree alone did not reconstruct the same evidence bytes
under both default Windows and LF-preserving checkouts: a small set of
historical records intentionally used CRLF bytes, while the rest of the
evidence graph expected LF bytes.

The release candidate corrects that portability defect with a path-specific
`.gitattributes` contract. It does not rewrite frozen evidence, change any
scientific value, retrain a model, or expand a claim. The corrected candidate
is verified from clean default-Windows and LF-preserving checkouts before Gate
D review. The original failed audit remains a failed historical observation;
the later repair does not retroactively relabel it.

This correction and its verification were substantially AI-assisted. They do
not establish applicant-performed independent reproduction. PlateGauge makes
no such claim. Release status must be determined from the exact `v1.0.0` tag,
its `release/gate-d-approval.json` record, and the post-deployment checks—not
from this note alone.
