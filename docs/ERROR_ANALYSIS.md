# Error analysis

> **Frozen ranking complete; Gate C review completed 20 September 2026.** The
> immutable ranking is in `reports/error_analysis.json`. AI-assisted visual
> annotations are kept separately in `reports/error_review_annotations.csv` so
> they cannot alter the predictions or confirmatory metrics. They are
> hypotheses, not adjudicated label corrections.

In the primary outer prediction tables, fields named `q05` and `q95` are the
empirically corrected and clipped interval endpoints, not separately preserved
raw model quantiles. Width and containment below use those corrected endpoints;
`q50` is unchanged.

## Largest-error summary

The twenty largest absolute errors span 11 categories. Their mean absolute
error is `0.6434173179118841`, median `0.5948464658930206`, and maximum
`0.9798145890235901`. Fourteen are underpredictions and six are
overpredictions. Only three would be retained by the frozen width rule, but the
uncertainty gate still fails overall because retention is extremely selective.
Six of the twenty corrected intervals miss the target.

| Rank | Sample | Category | Target | q50 | Absolute error | Width | Retained? |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | `lefood-0530` | 033 | 0.000000 | 0.979815 | 0.979815 | 0.712006 | No |
| 2 | `lefood-0320` | 015 | 0.854167 | 0.003189 | 0.850978 | 0.075565 | Yes |
| 3 | `lefood-0226` | 009 | 1.000000 | 0.160254 | 0.839746 | 0.897503 | No |
| 4 | `lefood-0400` | 023 | 0.000000 | 0.802848 | 0.802848 | 0.604943 | No |
| 5 | `lefood-0507` | 031 | 0.740741 | 0.000428 | 0.740313 | 0.058261 | Yes |

On this deliberately selected top-20 subset, after-only MobileNet has lower
absolute error in 17 cases and Ridge in all 20. Those conditional counts explain
the paired model's failure modes; they are not a general model-ranking statistic.

## Post hoc visual themes

The separate AI-assisted review marked these recurring visible conditions:

| Theme | Count among worst 20 |
|---|---:|
| Pair misalignment/translation/rotation | 15 |
| Oil or sauce residue change | 8 |
| Low-contrast rice or porridge | 6 |
| Glare or specularity | 3 |
| Boundary target one | 3 |
| Boundary target zero | 2 |

Eight cases also received explicitly defined post hoc tags, including large
object-scale change, structural appearance change, and possible image-to-mass
tension. These themes overlap and are descriptive, not causal findings.

The errors suggest a relational weakness: the network often reacts to position,
surface residue, or appearance change rather than reliably comparing remaining
quantity. The overall signed bias of `-0.060243876984511696` and target-slice
results show systematic underestimation away from exact-zero cases.

## Possible image-to-mass tensions

The review marked `lefood-0320`, `lefood-0400`, `lefood-0507`, and
`lefood-0530` as possible image-to-mass tensions. This wording is intentionally
non-adjudicative: the photographs, recorded masses, and observer scores can
disagree without proving which source is wrong. All four remain in the frozen
evaluation.

The post hoc sensitivity report excludes only those four to test whether the
central paired-versus-after-only direction reverses. It does not: paired macro
MAE is `0.1180232597071082`, after-only is `0.09315260329606655`, and the
difference remains `+0.02487065641104165`. This check cannot replace or modify
the confirmatory result.

## What is and is not established

- Established: the frozen top-20 ranking, numeric errors, interval containment,
  retained status, and descriptive annotations.
- Plausible: misalignment, low contrast, residue, and scale-change cues
  contribute to some failures.
- Not established: that any source label is wrong, that a theme causes an
  error, or that removing reviewed cases is a valid new benchmark.
- Gate C reviewed: the five-success/five-failure pack was reviewed and
  approved the memo's bounded interpretation. This does not adjudicate labels,
  establish independent contribution, or authorize publication.

## Evidence

- `reports/error_analysis.json`, evidence SHA-256
  `534b181e079c43fc23340f293cf3017f1e76221e00b88f08f84a2a46568f23b5`
  (file SHA-256
  `16d4cf8099e307692b102aedb1e17fda55145ec77ebf1f54426ed8028cf93df9`).
- `reports/error_review_annotations.csv`, SHA-256
  `17818944cfbc60662e10f7dcb3a8f5df3f7f9451971bba5d99792804339f8f6c`.
- `reports/label_sensitivity.json`, embedded evidence SHA-256
  `b394fb69a7c9d32468457df6f91224734db7dddfbf16bee4c01b46abb7e9ee09`.
