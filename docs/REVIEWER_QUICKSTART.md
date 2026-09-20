# Five-minute reviewer quickstart

PlateGauge is a fixed-example benchmark and failure explorer. It is not an
upload-based estimator, scale replacement, or food-waste impact claim. No raw
dataset download or model retraining is needed for this review.

## Minute 1 — read the outcome

Read the README's **At a glance** and **What the evaluation found** sections.
The essential result is paired MobileNet macro-category MAE `0.122756` versus
`0.097858` for after-only MobileNet. The paired-image hypothesis failed.

## Minute 2 — verify the machine evidence

Open `reports/results.json` and confirm:

- `dataset.valid_pairs = 514` and `dataset.categories = 34`;
- paired MobileNet macro-category MAE `0.12275587386595668`;
- after-only MobileNet macro-category MAE `0.09785758682716902`; and
- `decisions.benchmark_only = true`.

`docs/RESULTS.md` explains the same values in prose. The bootstrap interval is
conditional on the fixed run; it is not a population or retraining guarantee.

## Minute 3 — inspect failures, not only the average

Open `docs/ERROR_ANALYSIS.md` and `docs/ROBUSTNESS.md`. The largest errors,
interior-target underestimation, confidently wrong cases, and after-image blur
breach are why numeric estimation, interval, abstention, and robustness claims
are blocked.

## Minute 4 — inspect the public workflow

The six screenshots in `reports/media/` show the reviewed fixed-example journey.
The app accepts no visitor images and renders no live numeric model output. If
the locked environment is already installed, verify the browser evidence with:

```powershell
.\.venv\Scripts\python.exe scripts\verify_web_benchmark_evidence.py verify
```

This checks the generated visible values and examples against canonical frozen
sources; it does not retrain or modify evidence. The release candidate also
uses path-specific line-ending rules to reconstruct the same evidence bytes on
default-Windows and LF-preserving checkouts; see
`docs/REPRODUCIBILITY_NOTE.md`.

## Minute 5 — check reproducibility and boundaries

Read `docs/MODEL_CARD.md`, `docs/DATASHEET.md`, and
`docs/AI_ASSISTANCE_PUBLIC.md`, then read
`docs/REPRODUCIBILITY_NOTE.md`. `docs/TEST_REPORT.md` records 209 passed Python
tests, one intentional skip, and `85.51%` coverage for the configured
**non-training Python scope**;
`model.py`, `training.py`, and `export.py` are excluded from that coverage
measurement and are validated through separate focused tests and artifact
checks. No user study, field validation, external-site validation, or phone
performance result exists.
