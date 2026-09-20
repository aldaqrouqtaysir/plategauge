# Data Gate report — passing amended audit

> **Historical pre-fit checkpoint.** This report preserves the state when the
> amended data gate passed. The confirmatory evaluation was completed later;
> current outcomes and product boundaries are in `RESULTS.md`.

**Audit date:** 19 September 2026  
**Decision:** **PASSED — fitting authorized under the active amended protocol**  
**Amendment decision:** exact D011 correction applied and verified in D012  
**Boundary at issuance:** no baseline/model fitting result existed; Gate C/D
were unapproved

## Reproduced facts

| Check | Observed | Expected | Outcome |
|---|---:|---:|---|
| Workbook rows | 678 | 678 | Pass |
| Distinct non-empty food names | 50 | 50 | Pass |
| Matched image pairs | 524 | 524 | Pass |
| Rows without archived image pairs | 154 | 154 | Pass |
| Invalid mass-relation pairs | 10 | 10 | Pass |
| Primary valid pairs | 514 | 514 | Pass |
| Valid categories | 34 | 34 | Pass |
| Outer fold sizes | 103/103/103/103/102 | Same | Pass |
| Files present/decodable | `files_verified=true` | True | Pass |
| Cross-fold duplicate components | 0 | 0 | Pass |
| Manifest image hashes re-read | `hashes_verified=true` | True | Pass |
| Audit issues | `[]` | None | Pass |
| Overall audit | `passed=true` | True | **Pass** |

Evidence: `data/manifests/lefood_v1_audit.json`,
`lefood_v1_manifest.csv`, `lefood_v1_source_audit.csv`, and
`lefood_v1_duplicate_candidates.csv`. The exact before/after binding and scope
guard are recorded in `reports/data_gate/fold_amendment_applied.json` (SHA-256
`d5c27fdb6922aa871b95c7b036e6c9bb2f2f154fd182259e1b57723a10e8a7b6`).

Active artifact SHA-256 values:

- `configs/frozen_folds.json`:
  `feb8143a9d8e238cefd0b60f629f7313a9962a53cca54b9c6783293ccaa4ecbe`
- `configs/experiment.toml`:
  `58b9a9c1cdcfd4aa9dd6333f5bf29996e7123d01a7101c179b63af69166283a4`
- `data/manifests/lefood_v1_manifest.csv`:
  `0d8aae8e28b5aa8fcd5c35b89a40c7e90db55df893562043086485dde1f7ee16`
- `data/manifests/lefood_v1_audit.json`:
  `bd6322294895d474b1250b90e8f12c8a296ddf32156a8d5934a81367b1d63dd1`

## Source identity

- Local archive SHA-256:
  `19c43ca54caf006f91b22bbdbf45455de47e7e18d9dd98a071f3416697526859`
- Local workbook SHA-256:
  `82bacc92b57164e0ab74b0908c662dbfc0428ed4d230fb0ff04ac93176042fff`
- The two digests were independently recomputed locally. No publisher checksum
  was found, so they identify this download but are not an upstream authenticity
  proof.

## Original finding and resolution

The initial audit found that `dup-15f25e4070f6`, `dup-84e0fa596bc4`,
`dup-faf29cbb02fd`, `dup-c7a1ff728d7c`, `dup-d06da4f9b06c`, and
`dup-c67b65330d5d` crossed the original folds. The candidate report records their
exact relative paths, pHash distances, SSIM scores, and component IDs. The exact
D011 mapping was applied without changing records or fold sizes. The regenerated
audit now contains all nine duplicate components within folds and reports zero
cross-fold duplicate components.

## Approved correction — applied and verified

The exact hash-bound amendment in
`reports/data_gate/fold_amendment_candidate.json` (SHA-256
`92ddb108511ab082ede3606ca4f9cce75288c1186316ca7a9b1cb2b070040610`)
was approved before fitting. That mapping retains all 514 valid rows, preserves
fold sizes, keeps categories and duplicate-linked components atomic, and moves
exactly the eight categories listed in the candidate artifact. It was computed
before any fitting or outer result.

Approval alone did not change the then-current manifest, split configuration,
or failed audit. The implementation subsequently applied the exact mapping, and
the active hashes and passing audit above verify that required condition. The
approval is still not Gate C or Gate D approval.

## Historical fitting authorization and boundaries

At this checkpoint, the data gate authorized baseline/model fitting only under
the active fold config, manifest, audit, and frozen protocol. No fitting result
then existed and no outer result had been opened; the applied-amendment report
records both facts in its scope guard. The read-only experiment preflight
returned `status=ready`, no blockers, and protocol ID
`9450069d1260248bb5900c20c0b0784086513573735fb408c2bd2c85bb373e8f`.
Any change to the active inputs requires a new passing audit and matching
preflight before new fitting. Gate C claim/product selection and Gate D
release/deployment were unapproved at this checkpoint. Gate C was subsequently
approved only for the benchmark/failure-explorer form; Gate D remains separate.
