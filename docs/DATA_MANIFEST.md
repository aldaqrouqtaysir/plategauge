# Data manifest specification

**Status:** the exact D011 duplicate-safe correction is active and the regenerated
data audit **passed**. It reports 514 valid pairs across 34 categories, fold sizes
103/103/103/103/102, zero cross-fold duplicate components, `issues=[]`, verified
file/image hashes, and `passed=true`. The frozen confirmatory run is complete;
its evidence selected the benchmark/failure-explorer form rather than a numeric
estimator. No publisher checksum was found for an independent upstream
comparison.

## Source

| Field | Value |
|---|---|
| Name | LeFood-Set v1 |
| Landing page | https://data.mendeley.com/datasets/cchsk79jkt/1 |
| DOI | `10.17632/cchsk79jkt.1` |
| Version | 1 |
| License shown by provider | CC BY 4.0 |
| Intended local location | `data/raw/lefood-v1/` (Git-ignored) |
| Local archive SHA-256 | `19c43ca54caf006f91b22bbdbf45455de47e7e18d9dd98a071f3416697526859` |
| Local workbook SHA-256 | `82bacc92b57164e0ab74b0908c662dbfc0428ed4d230fb0ff04ac93176042fff` |
| Hash interpretation | Locally recomputed identifiers; no publisher-provided checksum located |

The initial audit reports 678 workbook rows, 524 matched image pairs in
categories `000`–`033`, 154 rows without archived images, ten matched pairs with
an invalid after-greater-than-before mass relation, and 514 primary valid pairs
across 34 categories. The missingness is structured: every source row in the 16
categories `034`–`049` lacks its archived image pair, so those food categories
are absent from the image benchmark rather than randomly missing within the 34
evaluated categories. This matches the planned count assertions but materially
limits coverage of the source workbook. Evidence:
`data/manifests/lefood_v1_source_audit.csv`,
`data/manifests/lefood_v1_audit.json`, and
`data/manifests/lefood_v1_manifest.csv`. The amended audit reports `passed=true`.

| Active artifact | SHA-256 |
|---|---|
| Frozen fold config | `feb8143a9d8e238cefd0b60f629f7313a9962a53cca54b9c6783293ccaa4ecbe` |
| Approved experiment config | `58b9a9c1cdcfd4aa9dd6333f5bf29996e7123d01a7101c179b63af69166283a4` |
| Primary manifest | `0d8aae8e28b5aa8fcd5c35b89a40c7e90db55df893562043086485dde1f7ee16` |
| Passing audit JSON | `bd6322294895d474b1250b90e8f12c8a296ddf32156a8d5934a81367b1d63dd1` |
| Applied-amendment binding report | `d5c27fdb6922aa871b95c7b036e6c9bb2f2f154fd182259e1b57723a10e8a7b6` |

## Unit of analysis

One row represents one matched before/after image pair for one food item and
its recorded before/after masses. The target is:

```text
leftover_fraction = recorded_weight_after_g / recorded_weight_before_g
```

A primary row requires a positive finite before mass, finite nonnegative after
mass, `after <= before`, two decodable images, and a provable mapping between
the workbook and the filenames.

The frozen target distribution contains 207 exact-zero and 47 exact-one rows;
254/514 (`49.4%`) of valid targets therefore lie at a boundary. Aggregate error
must be interpreted beside the predefined target-range slices.

## Required manifest columns

| Column | Meaning |
|---|---|
| `schema_version` | Manifest schema, currently `1.0` |
| `sample_id` | Stable generated sample identifier |
| `source_row` | One-based workbook row, including the header-row offset |
| `food_name`, `category` | Source label and three-digit grouping used for splitting/analysis |
| `before_path`, `after_path` | Paths relative to the local raw-data root |
| `before_mass_g`, `after_mass_g`, `leftover_fraction` | Source masses and derived target |
| `observer_score` | Contextual reference only; never a feature |
| `before_width`, `before_height`, `after_width`, `after_height` | Decoded dimensions |
| `before_sha256`, `after_sha256` | Cryptographic content identities |
| `duplicate_group` | Connected component of exact/confirmed near duplicates |
| `is_valid`, `exclusion_reason` | Auditable inclusion decision |
| `outer_fold` | Preregistered category-disjoint fold assignment |
| `source_doi`, `dataset_version`, `license` | Source provenance and rights fields |

The exact emitted schema is defined by `src/plategauge/schema.py` and
`data/manifest.schema.json`. It intentionally does not contain pHashes or a
same-category diagnostic fold; pHash/SSIM evidence belongs in the separate
duplicate-candidate report, and any diagnostic split requires its own versioned
artifact. The released manifest preserves source-relative paths, provenance,
hashes, decisions, and outer folds. Raw images are not committed.

## Duplicate policy

Exact SHA-256 matches and confirmed near duplicates must stay in one split.
Near-duplicate candidates are generated when pHash Hamming distance is ≤4 and
confirmed only when SSIM is ≥0.995 under a documented deterministic alignment.
Connected components—not isolated pair comparisons—define duplicate groups.
Suspected but unconfirmed cases are recorded for manual inspection; the audit
must not silently discard them.

## Active frozen category-disjoint outer folds

| Fold | Held-out categories and counts | Active n |
|---|---|---:|
| 0 | `001(78), 005(2), 019(14), 022(6), 032(3)` | 103 |
| 1 | `002(76), 008(4), 010(9), 014(14)` | 103 |
| 2 | `009(21), 011(18), 012(16), 016(5), 025(1), 028(5), 029(26), 033(11)` | 103 |
| 3 | `003(1), 006(2), 013(22), 015(20), 017(5), 021(12), 026(19), 031(22)` | 103 |
| 4 | `000(1), 004(17), 007(17), 018(4), 020(6), 023(22), 024(21), 027(3), 030(11)` | 102 |

D011 approved and D012 verified this exact mapping. It retains every valid row
while preserving category/component atomicity, balance, and exact fold sizes.
The regenerated audit confirms that all duplicate components are contained
within folds. Any data, duplicate-rule, or split change requires a new passing
audit before any new fitting or evaluation.

## Evaluation-output semantics

For the primary outer paired-MobileNet prediction tables, the legacy columns
named `q05` and `q95` contain the **empirically corrected and clipped interval
endpoints** written after applying each fold's inner-derived correction. They
are not preserved raw model quantiles. `q50` remains the point prediction.
The exported ONNX model emits the raw ordered three-value model output; the
failed public interval gate means neither form is presented as a reliable or
guaranteed user interval. A future schema should retain raw quantiles and
corrected endpoints in separate columns.

## Exclusion ledger

The emitted matched-pair manifest currently uses
`after_mass_exceeds_before_mass` for the ten invalid target relations. Workbook
rows whose referenced images are unavailable remain in the separate source
audit with status `missing_image` and a filename-specific reason; they are not
fabricated as matched manifest rows. Schema/decode/path/hash failures stop the
build rather than silently receiving a generic exclusion code. The ten invalid
mass rows may appear only in a labeled clipped-label sensitivity analysis, never
the primary result.

## Release integrity

The locally recomputed archive and workbook hashes above identify the exact
source used, but they are not an upstream authenticity proof because no
publisher checksum was found. Also record SHA-256 for the source image inventory,
audit report, primary manifest, exclusion ledger, duplicate report, fold map,
and any example assets. The artifact manifest must bind them to the evaluation
commit. The active fold, manifest, and passing-audit hashes are recorded above;
rerun the audit with image-hash verification after any relevant change.
