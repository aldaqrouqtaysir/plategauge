# Data and model licensing

This is an engineering license inventory, not legal advice. Release is blocked
until every distributed artifact has a verified source and compatible terms.

## LeFood-Set v1

- Source: https://data.mendeley.com/datasets/cchsk79jkt/1
- DOI: `10.17632/cchsk79jkt.1`
- Creators: Yuita Arum Sari, Yudi Arimba Wani, and Atsushi Nakazawa.
- Provider-displayed license: Creative Commons Attribution 4.0 International.
- License text: https://creativecommons.org/licenses/by/4.0/
- Actual v1 use: local training/evaluation, derived manifests, ten attributed
  fixed-example pairs in the local candidate, and a trained benchmark artifact.
- Required release treatment: credit dataset creators, link the source/DOI and
  CC BY 4.0, identify modifications/derivatives, and do not imply endorsement.
- Raw archive/images: not redistributed by default. Users acquire them from the
  source.
- Locally recomputed archive SHA-256:
  `19c43ca54caf006f91b22bbdbf45455de47e7e18d9dd98a071f3416697526859`.
- Locally recomputed workbook SHA-256:
  `82bacc92b57164e0ab74b0908c662dbfc0428ed4d230fb0ff04ac93176042fff`.
- No publisher checksum was found; these values identify the local source and do
  not independently prove upstream authenticity.

The candidate treats the weights and fixed examples conservatively as
dataset-derived material: dataset attribution, source/license links, and change
notices accompany them even though the original project code remains
Apache-2.0. This recorded position does not constitute legal advice or imply
dataset-author endorsement.

## Pretrained encoder

- Used checkpoint: https://huggingface.co/timm/mobilenetv3_small_100.lamb_in1k
- Pinned revision: `1824797e7887cbec1990e4adbd6675960a36c589`.
- Pinned `model.safetensors` SHA-256:
  `46d2c063b18125884c48937afa4c49e18128869e52e8db96df48bf0a4d7ff697`.
- Displayed license: Apache-2.0.
- Candidate treatment: preserve upstream notices and the pinned identity; the
  release workflow must recheck the exact approved bundle before distribution.

DINOv2 and ResNet comparison artifacts are research dependencies only unless a
release-specific license audit permits distribution. Their outputs may be
reported without bundling their checkpoints.

## Project code

Original source code and documentation are Apache-2.0. This does not relicense
dataset files, model weights, dependency code, fonts, icons, or screenshots.

## Excluded sources

FLIC and any source with ambiguous redistribution/training terms are excluded
from v1. No “publicly downloadable” source is presumed licensed.

## Release checklist

- [ ] Capture source-page PDFs or metadata snapshots and access date.
- [x] Record local dataset archive/workbook hashes and dataset attribution in
      `NOTICE` and `CITATION.cff`.
- [x] Pin checkpoint revision/hash and preserve its license/notice.
- [x] Generate current dependency license inventories from the locked Python
      environment and production JavaScript lockfile in `reports/security/`.
      Regenerate and review them again for Gate D.
- [x] Review the ten fixed-example pairs, attribution, and change notices in the
      exact local candidate.
- [x] Review trained-model attribution and the model-card license field for the
      exact local candidate.
- [x] Check that `LICENSE`, `NOTICE`, `CITATION.cff`, README, model card, and web
      About page agree in the local candidate.
- [x] Confirm the prospective public source tree and exact static candidate do
      not contain the raw archive or workbook. The approved tagged tree must be
      checked again before release.
