# Robustness report

> **Perturbation sensitivity complete; no robustness claim is allowed.** These
> tests run the final model trained on all 514 pairs over those same 514 source
> pairs. They diagnose input sensitivity and misuse behavior; they are not
> held-out accuracy estimates and do not replace the confirmatory outer folds.

The clean reference macro-category MAE is `0.11568785572290101`. Under the
frozen downgrade rule, any routine perturbation with a delta above `0.03`
requires narrower capture guidance and prohibits a robustness claim.

| Condition | Mode/severity | Macro MAE | Delta from clean | Breach? |
|---|---|---:|---:|---|
| Shared rotation +5° | Shared | 0.116034 | +0.000346 | No |
| Shared rotation −5° | Shared | 0.123865 | +0.008177 | No |
| Shared translation +5% | Shared | 0.118730 | +0.003042 | No |
| Shared center crop 5% | Shared | 0.106334 | −0.009353 | No |
| JPEG quality 50 | Shared | 0.112889 | −0.002799 | No |
| Brightness +20% | Shared | 0.122410 | +0.006722 | No |
| Brightness −20% | Shared | 0.109530 | −0.006157 | No |
| Contrast +20% | Shared | 0.118573 | +0.002885 | No |
| Contrast −20% | Shared | 0.108960 | −0.006728 | No |
| Gaussian blur σ=1 | Shared | 0.128789 | +0.013101 | No |
| After brightness +20% | After only | 0.126414 | +0.010726 | No |
| **After Gaussian blur σ=1** | **After only** | **0.150220** | **+0.034533** | **Yes** |
| After translation +5% | After only | 0.132941 | +0.017253 | No |

The only routine breach is blur applied to the after image:
`+0.034532527658502635`. The release therefore must instruct users to avoid
blur, hold both images to comparable focus and capture conditions, and make no
field/smartphone/robustness claim.

## Misuse probes

| Misuse | Macro MAE | Delta from clean |
|---|---:|---:|
| Same before image in both slots | 0.611071 | +0.495383 |
| Swapped before/after order | 0.163347 | +0.047659 |
| Unrelated after image | 0.394109 | +0.278421 |

Misuse probes do not trigger the routine downgrade rule, but they show that the
model can produce outputs on semantically invalid pairs. Structural file checks
cannot prove that two photographs depict the same item. A public failure
explorer should expose this limitation rather than imply automatic semantic
validation.

## Decision

- `robustness_downgrade_required = true`.
- No claim of robustness to routine capture variation is permitted.
- No smartphone, field, hospital, UAE, or uncontrolled-photography claim is
  permitted.
- Gate C approved the benchmark/failure-explorer form on 20
  September 2026, with this no-robustness boundary intact. Gate D was
  unapproved at the source-freeze review; any later release authority cannot
  turn this failed gate into a robustness claim.

Canonical evidence is `reports/robustness.json`, embedded evidence SHA-256
`f62a467bfa64e74c904143e3e72bce99d53f4bd97fce8419ae60f855d0cfe0c2`.
The routine-delta figure is
`reports/figures/gate_c_routine_robustness_delta.svg`.
