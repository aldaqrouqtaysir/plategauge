# Datasheet for the PlateGauge benchmark subset

**Status:** exact duplicate-safe correction applied; regenerated data audit
passed with verified hashes and zero cross-fold duplicate components. The
frozen confirmatory evaluation is complete and supports only a benchmark and
failure explorer.

## Motivation

PlateGauge uses LeFood-Set v1 to test whether paired images can estimate the
recorded fraction of a single food item remaining. The dataset was not created
by PlateGauge, and PlateGauge does not claim its original collection was
designed for category-shift deployment evaluation.

## Composition

The source includes structured records and before/after food images from a
controlled Indonesian hospital context. The generated audit found 678 workbook
rows, 524 matched pairs, 154 rows lacking archived image pairs, and 514 primary
valid pairs across 34 source categories after flagging ten invalid mass
relations. These counts match the preregistered expectations. The exact D011
correction is active, all nine duplicate components are contained within folds,
and the audit reports `passed=true` and `issues=[]`. All 154 missing-image rows
belong to the 16 source categories `034`–`049`; the evaluated image subset is
therefore a structured block of categories `000`–`033`, not a random sample of
the full 50-category workbook. Local archive/workbook hashes are recorded, but
no publisher checksum was found for independent upstream comparison.

One observation contains two images, two recorded masses, source category/name,
and optionally an observer assessment. The derived target is a continuous
fraction in `[0,1]`. Category and observer fields support splitting/analysis;
they are not model inputs. The valid subset includes 207 exact-zero targets and
47 exact-one targets, so 254/514 (`49.4%`) lie at an endpoint.

## Collection and provenance

Consult the [dataset landing page](https://data.mendeley.com/datasets/cchsk79jkt/1)
and [associated paper](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0320426)
for the collectors' description. PlateGauge must not paraphrase details not
confirmed in those sources. It did not obtain direct participant, hospital, or
collector consent and relies on the public CC BY 4.0 release for this research
use.

## Processing

- Map source rows to image pairs and retain source-relative filenames.
- Decode images, record dimensions and SHA-256, and derive the mass ratio.
- Exclude invalid primary mass relations without erasing them from the ledger.
- Construct exact/near-duplicate connected components.
- Assign intact components and food categories to frozen outer folds.
- During modeling, resize/crop and normalize images using the pinned
  pretrained-model transform; augment only training inputs.

Processed manifests must retain enough provenance to reproduce every decision.
Raw images stay outside Git.

## Known limitations

- Small sample and highly unequal category sizes; several categories have one
  or two valid pairs.
- Structured source coverage: all 16 categories `034`–`049` lack archived image
  pairs and are absent from the benchmark. Their performance cannot be inferred
  from results on categories `000`–`033`.
- Endpoint prevalence is high (`49.4%` exact zero or one), while the predefined
  interior target slices have materially higher error than exact zero.
- A single controlled acquisition context does not represent other institutions,
  countries, cuisines, serving practices, containers, lighting, or devices.
- Mass differences of a few grams may reflect measurement noise; exact instrument
  calibration and repeated-measure uncertainty are not inferred unless the
  source documents provide them.
- “Food category” is a source grouping, not a demographic or universal cuisine
  taxonomy.
- The observer score is contextual prior art, not an unbiased ground truth.
- Paired images may contain capture cues that do not survive real deployment.

## Appropriate uses

- Reproducible benchmark research on paired visual leftover-fraction estimation.
- Category-disjoint generalization and failure analysis.
- Local, fixed-example demonstration of the frozen benchmark and its failure
  modes.

## Inappropriate uses

Clinical intake, nutrition, calorie estimation, individual monitoring, billing,
procurement, employee performance, compliance, autonomous decisions,
surveillance, unconsented identity analysis, or claims about arbitrary food or
UAE/Indonesian hospital deployment.

## Maintenance

Version the source archive and every processed manifest. If the upstream source
changes, do not replace files in place: create a new manifest version, reproduce
the audit, and keep prior hashes. Public scientific decisions and corrections
must be described in `RESEARCH_DECISIONS.md` or a versioned release note.
