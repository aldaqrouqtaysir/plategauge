# PlateGauge system card

> **Source-freeze status on 20 September 2026:** Gate C approved PlateGauge as
> a static benchmark and failure explorer. At this pre-Gate-D review point it
> was not deployed, Gate D had not been approved, and the product did not
> provide estimates for visitor-supplied images. Any later release must be
> verified from the approval record, tag, release manifest, and public smoke
> evidence rather than inferred from this system card.

## Current purpose

PlateGauge makes a frozen study of leftover-fraction prediction inspectable.
It reports the category-disjoint benchmark, compares the paired MobileNet with
the after-only ablation and other baselines, and lets a reviewer inspect ten
attributed LeFood-Set records: five selected close predictions spanning the
target range and the five largest paired-model errors.

The explorer is an evidence and communication artifact, not a measurement
tool. The paired model's macro-category MAE was `0.12275587386595668`, compared
with `0.09785758682716902` for the after-only ablation. The public numeric-demo,
interval, useful-abstention, and robustness claim gates also failed. The
current system therefore accepts no visitor images or mass, computes no
per-user result, and cannot support operational, clinical, or waste-reduction
decisions.

## Current components

| Component | Current responsibility | Trust boundary | Failure response |
|---|---|---|---|
| Frozen research evidence | Category-disjoint predictions, metrics, gates, figures, and example selection | Hash-bound data, protocol, run, model, and generated reports | A mismatch blocks release; it is never repaired from a displayed result |
| Static evidence module | Encodes the reviewed metrics and the ten disclosed example records used by the interface | Values must agree with frozen machine-readable evidence | Tests and the release audit fail on divergence |
| Main explorer route | Displays study design, comparisons, examples, failed gates, attribution, and limitations | Visitors may select only the bundled records; there is no free text, file input, camera, or mass field | Missing or inconsistent assets block the candidate; no estimate fallback exists |
| Bundled example assets | Twenty attributed before/after JPEGs for ten fixed LeFood records | Exact allowlist and hashes; CC BY 4.0 attribution and change notices | Missing, extra, or changed images block the release bundle |
| Unlinked fixed-pair harness | On the explicit `?benchmark=1` route, replays the frozen ONNX model on a selected bundled pair for integrity and device-timing checks | Fixed allowlisted images, release manifest, same-origin worker/model/WASM | Reports replay unavailable or failed; discards the numeric model output |
| Release bundle and audit | Binds static assets, model identity, notices, privacy text, and network policy | Reviewed local build; no source tag or public host yet | Any unexpected file, request, hash, path, secret, or license issue blocks Gate D |
| Potential GitHub Pages host | May serve the reviewed static bundle only after explicit Gate D approval | GitHub and ordinary browser/network metadata are outside PlateGauge's application boundary | At source freeze no deployment existed; local build and screenshots were the fallback |

The ordinary explorer route does not initialize the model or perform
inference. The query-only harness is unlinked from that route, accepts no
custom input, and renders only cycle status, model version, and timing—not the
model's numeric prediction. Replaying a bundled training record is not
evaluation evidence.

## Data and trust boundaries

- The displayed images and values are fixed project artifacts, not visitor
  data. The interface exposes exactly the records named in its reviewed
  allowlist.
- Model inputs in the local harness originate only from those bundled assets.
  A visitor cannot supply an image, URL, filename, category, or mass.
- Research code and raw LeFood data remain outside the production bundle. The
  displayed evidence is derived from frozen outer-fold predictions; the
  browser does not recalculate the evaluation.
- The candidate uses same-origin static assets and contains no PlateGauge
  application API. Any future static host and the visitor's browser, device,
  extensions, DNS provider, and network remain separate trust domains.
- Gate C approved the product form and claim boundaries. It did not approve
  the build, a commit or tag, deployment, application use, or Gate D.

## Privacy behavior

The current explorer has no image upload, camera access, personal-image
processing, user-supplied mass, account, database, analytics, advertising,
cookie, telemetry, prediction history, or error-reporting service. It creates
no per-user numeric prediction and sends no visitor content to a PlateGauge
server because no such server exists.

The local production-route test captures requests from first navigation and
allows only reviewed same-origin static assets. The fixed-pair harness loads
bundled images, the model, and WASM from that same origin; it does not transmit
or retain a numeric inference result. This does not promise anonymous
browsing: a future GitHub Pages host and ordinary internet infrastructure may
process request metadata.

## Safety, misuse, and communication controls

The main foreseeable misuse is interpretive rather than transactional:
someone could mistake fixed records for new estimates, cherry-pick close
examples, hide the failed paired-image hypothesis, or extend one controlled
Indonesian hospital dataset to unrelated foods and settings. Controls are:

- label every image pair as a frozen benchmark record;
- disclose that the close examples are selected rather than random;
- show the five largest errors beside the selected close predictions;
- foreground that after-only inference outperformed the paired model;
- show no custom-image estimate, remaining-mass value, empirical interval, or
  abstention decision;
- provide no downstream decision API or automated action; and
- prohibit clinical, nutritional, procurement, billing, surveillance,
  scale-replacement, UAE-wide, smartphone, production, and realized-impact
  claims.

No demographic fairness claim is supported. Relevant disparity and
external-validity analysis is limited to food category, target range, support,
observer level, visual failure themes, and the dataset's narrow acquisition
context.

## Runtime and integrity failures

- A missing or altered evidence, example, model, manifest, notice, or runtime
  asset blocks the reviewed release bundle.
- A fixed-pair harness initialization, preprocessing, worker, or inference
  failure produces an explicit unavailable/error state and no number.
- An unexpected network request, remote runtime asset, or extra built file
  fails the production audit.
- A new custom-input route, newly rendered inference number, or weakened claim
  boundary is a product-scope change requiring fresh evaluation and approval;
  it is not a patch to this explorer.

## Monitoring and maintenance

At the 20 September 2026 source freeze, there was no live service or production
monitoring because no deployment had been authorized. Local checks cover
frozen-evidence identity, the exact static bundle, accessibility, keyboard
behavior, fixed-example display, no custom input, suppression of numeric
replay output, model parity, and allowlisted network traffic. Dependency and
license observations are time-sensitive and must be refreshed by the approved
release workflow.

If Gate D authorizes deployment, the release plan requires a post-deploy smoke
check for the URL, model checksum, fixed example, notices, links, and network
boundary, followed by a weekly static smoke check through the supported release
period. A release must carry those separate records; this pre-approval card is
not evidence that deployment occurred.

## Historical pre-outcome estimator design

> **Historical design only; not current or releasable behavior.** Before the
> frozen results were opened, PlateGauge was designed to validate a visitor's
> before/after files, preprocess them in Canvas, run a shared-encoder ONNX model
> in a Web Worker, and return an `estimate`, `abstain`, or `invalid_input`
> result. The proposed estimate could include a calibrated interval and a
> user-mass conversion only if preregistered gates passed.

The repository retains parts of that validator, preprocessing, result-schema,
worker, and test implementation as an auditable engineering record. Failed
product gates mean they do not authorize—or appear as—a visitor workflow. Any
future custom-image estimator would be a separately scoped and evaluated
version with renewed privacy, safety, security, and Gate D review.

## Governance snapshot at source freeze

On 20 September 2026, when this source-freeze card was prepared:

- frozen scientific evidence was complete and unchanged;
- Gate C approved a benchmark/failure explorer with the
  review memo's claim boundaries;
- the local release-candidate audit had passed its technical checks with no
  failed checks, while release remained blocked on Gate D actions and the
  technical result granted no release authority;
- Gate D approval, source commit, tag, remote, public URL, deployment, and live
  public smoke evidence were absent; and
- independent frozen-path reproduction, contribution wording review,
  and public-claim sign-off were not completed.

Any later status belongs in the commit-bound release manifest, Gate D approval
record, deployment record, and post-deploy smoke evidence.
