# Release evidence tooling

These commands are post-training tools. They do not train a model, open an
outer fold, download weights, deploy the site, or create a performance claim.
They fail closed unless the final checkpoint is bound to the approved protocol,
the D014 final-selection rule, the complete immutable task recipe, and the
recorded experiment runner.

## Final robustness evaluation

After the final 514-pair checkpoint exists:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_final_robustness.py `
  --experiment-directory reports\experiments\confirmatory `
  --dataset-root "data\raw\lefood-v1\LeFood-Set Leftovers Food Dataset\LeFood-Set"
```

The command re-hashes the dataset, loads the final paired MobileNet without an
implicit model download, and evaluates all 514 valid pairs under the clean
condition, thirteen frozen image perturbations, same-image misuse, swapped
order, and a deterministic unrelated-after-image derangement. It creates
`reports/robustness.json` once. Every condition contains macro-category MAE,
its delta from clean, all sample predictions, and a digest of those predictions.
Only routine perturbations can trigger the documented `> 0.03` robustness
downgrade; misuse measurements remain diagnostic.

## Frozen ONNX export

```powershell
.\.venv\Scripts\python.exe scripts\export_frozen_model.py `
  --experiment-directory reports\experiments\confirmatory `
  --dataset-root "data\raw\lefood-v1\LeFood-Set Leftovers Food Dataset\LeFood-Set"
```

The exporter constructs the architecture with `pretrained=False`, loads the
full frozen state dictionary strictly, exports through a temporary directory,
and publishes only after both gates pass: no more than 15,000,000 bytes (15 MB,
decimal) and maximum
PyTorch-to-ONNX drift of `1e-4` on eight deterministic manifest pairs. The
immutable evidence sidecar records the ONNX byte count and SHA-256, parity
input digest and sample IDs, frozen selection/config/task hashes, and dataset
verification. Existing model or evidence files are never overwritten.

## Python-to-browser preprocessing goldens

The checked-in fixtures are generated and verified with:

```powershell
.\.venv\Scripts\python.exe scripts\generate_preprocess_golden.py verify
cd web
pnpm exec playwright test tests/e2e/preprocess-golden.spec.ts
```

`identity_pattern.png` verifies every center-cropped RGBA byte, channel order,
and float32-normalized tensor byte without interpolation. Uniform landscape and
portrait fixtures verify resize geometry exactly. For these two uniform
fixtures only, WebKit compatibility permits at most one RGB level per channel;
alpha must remain within 254–255 and every tensor value must exactly normalize the
observed pixels. Chromium and Firefox retain exact RGBA/tensor hashes for all
fixtures; WebKit retains exact hashes for the patterned identity fixture.
This synthetic-fixture check does not establish image parity on real photos.
The worker uses explicit `Math.fround`
steps so its ImageNet normalization matches NumPy float32 operations. The
Playwright test runs in the normal Chromium, Firefox, and WebKit matrix.

The committed PNG, tensor, and manifest hashes remain verified. Regenerating
synthetic source PNGs may produce different lossless compression bytes across
Pillow/zlib builds; the regeneration test therefore compares decoded pixels
exactly as well as geometry and normalized-tensor hashes. Browser observations
are attached to test reports so platform failures can be inspected numerically.
Each fixture runs as an independent test, so one failure cannot prevent the
other observations. The bounded alpha allowance follows the reviewed D-R2
diagnostics documented in `MAINTENANCE_1_0_1.md`; alpha is not a model input.
It does not alter production pixels, golden bytes, or the RGB/tensor limits.

## Browser performance gate

The schema is
`release/browser-benchmark-measurement.schema.json`. A human or benchmark
harness must populate a real `status: "measured"` record with at least three
warmups, twenty warm inference durations, transfer-derived first-load bytes,
and a documented peak-memory method on a physical reference laptop. The
completed evaluated output is `reports/browser_benchmark.json`; its source
measurement SHA-256 is
`3c194e85724fda14550253a7994c34bd0c46026722cc80d1733767cb042a71f1`.

After collecting and reviewing that record:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_browser_benchmark.py `
  path\to\real-measurement.json `
  --model artifacts\plategauge.onnx `
  --release-evidence artifacts\plategauge.onnx.evidence.json
```

The evaluator checks both byte bindings, derives nearest-rank warm p50/p95,
and evaluates the frozen `p95 <= 1500 ms` and peak-memory `<= 512 MB` gates. A
failed measurement is preserved as failed evidence. The output explicitly
forbids phone or unmeasured-browser performance claims.

The completed headed-Chrome reference run used 3 warm-ups and 20 measurements.
It reports p50 `18.78000009059906` ms, p95 `22.119999885559082` ms,
`45.64192485809326` MiB peak application memory using
`performance.measureUserAgentSpecificMemory`, and `25,128,921` first-load body
bytes. Both gates passed. Evidence digest:
`77dc5e9ee873fc453f6a081926dc2259f675c6fbf39a5e1e3e73f5053bf77be9`.
