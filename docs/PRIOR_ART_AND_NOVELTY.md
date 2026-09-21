# Prior art and defensible differentiation

This is not a claim of exhaustive novelty. Searches covered research papers,
open-source repositories, commercial systems, accessibility guidance, public
initiatives, and benchmark tasks. Safe language is based on workflow and
evaluation differences—not “first” or “never done before.”

The recorded search is not a complete census of student projects, hackathons,
or private deployments. PlateGauge's differentiation therefore never depends
on their absence; it depends only on the explicitly tested combination of
paired inputs, held-out categories, baselines, uncertainty gates, and local
browser execution.

## Paired food-leftover fraction estimation

| Prior or adjacent work | Similarity | Relevant difference or limitation |
|---|---|---|
| [LeFood-Set paper](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0320426) | Same source dataset and visual leftover estimation | PlateGauge preregisters category-disjoint nested evaluation, paired-value ablations, empirical uncertainty gates, and local browser artifact verification; its results are not directly comparable if protocols differ |
| [LeFood-Set v1](https://data.mendeley.com/datasets/cchsk79jkt/1) | Paired images, masses, and observer records | Dataset source, not a competing product; license and selection bias remain controlling constraints |
| [FLIC dataset/paper](https://www.mdpi.com/2076-3417/16/11/5465) | Paired tray imagery, masks, and measured leftovers | More operationally rich, but the public-data license was not sufficiently explicit for this project; excluded |
| [Winnow Vision](https://www.winnowsolutions.com/) | Commercial visual food-waste measurement | Operational hardware/service and broad workflow; PlateGauge is a small open research demonstrator with no impact claim |
| [Leanpath](https://www.leanpath.com/) | Commercial food-waste measurement and analytics | Operational platform; PlateGauge does not offer analytics, procurement, or reduction programs |
| [Orbisk](https://orbisk.com/) | Camera-assisted professional kitchen waste monitoring | Real deployment ecosystem; PlateGauge uses standardized paired images and makes no kitchen-deployment claim |
| [KITRO](https://www.kitro.ch/) | Automated food-waste data collection | Hardware/analytics platform rather than a public category-shift benchmark |
| [Lumitics Insight](https://lumitics.com/) | Smart-bin food-waste tracking | Different capture hardware and operational setting |
| [Nutrition5k](https://github.com/google-research-datasets/Nutrition5k) | Food images with mass/nutrient labels | Meal/nutrition estimation, not before/after leftover fraction; PlateGauge excludes nutrition |
| [FoodSeg103](https://arxiv.org/abs/2105.05409) | Food-image segmentation benchmark | Semantic segmentation rather than remaining-fraction regression |
| [UNEP Food Waste Index](https://www.unep.org/resources/publication/food-waste-index-report-2024) | Establishes the measurement problem | Evidence source, not an algorithm or product |
| [ne'ma](https://www.nema.ae/en/baseline/faqs) | UAE initiative concerned with food loss and waste | Policy/context source; no partnership or UAE validation is claimed |

**Defensible differentiation:** an openly documented compact paired-image
benchmark pipeline with category-disjoint evaluation, an after-only ablation, a
destructive mismatch control, empirical uncertainty gating, and same-origin
browser artifact verification. Each component has precedent; the contribution is the
disciplined combination under narrow constraints. The mismatch control replaces
the after image and therefore does not isolate the incremental value of the
before image.

**Novelty risk:** medium. The visual estimation task and commercial workflows
already exist. The frozen paired model did not beat the after-only ablation, so
v1's value is the transparent negative result, reproducible evaluation, and
failure analysis—not a claim of a superior estimator.

**Safe public wording:** “PlateGauge evaluates a compact paired-image model on
LeFood-Set under held-out food categories and presents the failed paired-value
hypothesis, fixed examples, and failure analysis in a local browser explorer.”

**Prohibited wording:** first, unique, state of the art, production ready,
clinically validated, UAE validated, replaces a scale, provides a useful
interval or abstention system, or reduces food waste.

Internal project-selection comparisons and discarded concepts are not part of
the prospective public source tree. They neither support nor weaken the narrow
PlateGauge claims above.
