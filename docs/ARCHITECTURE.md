# Architecture

**Source-freeze snapshot (20 September 2026):** this architecture described the
Gate C-approved local benchmark/failure-explorer candidate. It had not been
deployed, and Gate D had not been approved at this checkpoint.

## Current Gate C-approved system

```text
Frozen research artifacts
  metrics + slice summaries + error records + attributed example images
                              |
                              v
                 static React/TypeScript explorer
                              |
                              v
 aggregate comparisons + fixed example views + limitations

Unlinked local benchmark harness (verification only)
  bundled fixed pair -> deterministic preprocessing -> Web Worker
                     -> ONNX Runtime Web, single-threaded WASM
                     -> timing/integrity status; numeric output suppressed
```

The visible candidate is a benchmark and failure explorer. It has no arbitrary
file input, user-mass field, remote-inference fallback, per-user prediction,
interval display, or abstention product. Its examples and numeric values are
frozen study records, not fresh estimates.

The unlinked `?benchmark=1` route exists only for reproducible physical-browser
timing of the frozen artifact with a bundled pair. That pair was used in
all-data training, so the route deliberately does not render or retain its
numeric model output and cannot be used as evaluation evidence.

## Research pipeline

```text
LeFood-Set v1 (local, ignored)
  -> audit + pairing + hashes + duplicate graph
  -> immutable manifest + category-disjoint folds
  -> baseline / nested model training
  -> outer-fold predictions + metrics + robustness
  -> selected all-data training configuration
  -> ONNX export + parity and integrity checks
  -> frozen evidence consumed by the static explorer
```

- `src/plategauge/data`: source discovery, row/image pairing, validation,
  hashing, perceptual duplicate grouping, manifest generation, and frozen folds.
- `src/plategauge/features`: deterministic handcrafted RGB/HSV histogram, SSIM,
  edge-density, foreground-occupancy, and difference features.
- `src/plategauge/models`: median/Ridge baselines; shared encoders; ordered
  quantile head; loss; training freeze/unfreeze schedule.
- `src/plategauge/evaluation`: predictions, macro/micro metrics, empirical
  interval analysis, abstention analysis, bootstrap, sign-flip tests, slicing,
  robustness, and artifact metadata.
- `src/plategauge/export`: ONNX export, parity set, checksums, optional
  quantization gate, and browser metadata.

No notebook is authoritative. Frozen configuration, command outputs, and
machine-readable evidence determine the results.

## Frozen research-model interface

The paired model takes two float tensors shaped `[N,3,224,224]`, normalized
with the pinned checkpoint preprocessing. A shared MobileNetV3-Small encoder
produces a 1,024-element pooled embedding for each image. Fusion concatenates
`before`, `after`, `abs(before-after)`, and `before*after`. The head is
`LayerNorm(4096) -> Linear(256) -> Hardswish -> Dropout -> Linear(3)`, followed
by a deterministic transformation producing ordered bounded low, median, and
high quantiles.

Food category, filenames, weights, observer values, and EXIF are prohibited
model inputs. This section documents the evaluated method; it does not define a
public inference service.

## Static explorer boundary

The candidate bundles attributed, fixed LeFood example images and frozen
summary data on the same origin. It has no CDN, API, model host, database,
account, telemetry endpoint, user-upload endpoint, or third-party script. The
model and WASM assets are needed only by the unlinked fixed-pair benchmark
harness. ONNX Runtime uses single-threaded WASM because GitHub Pages does not
supply the cross-origin isolation headers needed for threaded WASM.

Automated production-route tests restrict requests to the enumerated static
asset set. Network metadata created while loading a future hosted page remains
within the hosting/network boundary described in `PRIVACY_NOTICE.md`.

## Visible evidence contract

The visible UI reads frozen benchmark records and renders:

- aggregate and category/slice comparisons;
- fixed representative-success and largest-error examples;
- each example's recorded target, frozen outer-fold prediction, and absolute
  error; and
- explicit limitations and failed-gate explanations.

It does not call the estimator result union. `estimate`, `abstain`, and
`invalid_input` types remain an audit artifact of the superseded pre-outcome
design and low-level test coverage, not current user-facing states.

## Superseded pre-outcome browser design

> **Historical design only.** The preregistered plan contemplated local file
> validation, Canvas preprocessing, a worker-hosted ONNX model, a numeric result
> or abstention, and optional mass conversion. The frozen numeric-demo,
> interval, and useful-abstention gates failed, so that product flow was removed
> from the current interface. Retained modules must not be interpreted as an
> available upload-based estimator.

## Reproducibility and provenance

Any authorized release must bind the code revision; environment lockfiles;
dataset, manifest, split, configuration, pretrained-weight, prediction, result,
ONNX, and static-example hashes; seed; model version; build identifier; and
license inventory. The model artifact and the rendered explorer are never
treated as self-documenting. Gate D and deployment remain pending.
