# Public release checklist

> Historical source-freeze checklist. Counts and pending boxes below describe
> that checkpoint, not current deployment status. The v1.0.1 release attempt
> was blocked; the [v1.0.2 maintenance record](MAINTENANCE_1_0_2.md) describes
> the current unapproved correction. Exact-source review and passing release
> checks remain mandatory; no live deployment is established here.

Gate C was approved on 20 September 2026 for the benchmark/failure explorer and
the claim boundaries in the Gate C review memo. No release is authorized until
the named maintainer separately approves Gate D. Checked items below are
technical evidence only unless they explicitly record a human decision.

## Evidence

- [x] Data audit passes; counts, exclusions, hashes, and D011 amendment are
      documented.
- [x] Outer predictions contain every valid row exactly once for all eight
      workloads.
- [x] Result tables and deterministic figures derive from immutable evidence.
- [x] Gate C decision selects `benchmark_failure_explorer` with the
      Gate C review memo's claim boundaries.
- [x] Error, target-slice, interval, abstention, efficiency, robustness,
      same-category, and label-sensitivity analyses are complete and bounded.
- [x] Claim-evidence map blocks paired-value, numeric-estimator, interval,
      useful-abstention, robustness, field, clinical, impact, and SOTA overclaims.
- [x] The named maintainer reviewed the Gate C pack containing five selected successes,
      five largest failures, and all headline metrics before giving the exact
      D025 approval.

## Model and software quality

- [x] Final M2 epoch-6 checkpoint and exact FP32 ONNX are hash-bound to the
      frozen run.
- [x] ONNX size is below 15,000,000 bytes and parity drift is below `1e-4`.
- [x] Local benchmark-only release-candidate staging exists without deployment.
- [x] Final local Python verification recorded 209 passed, 1 intentional skip,
      and 85.51% coverage for the configured non-training scope
      (not whole-repository or training-code coverage), Ruff clean, and strict
      mypy clean.
- [x] Final local web verification recorded ESLint/strict TypeScript clean, 79
      Vitest tests, a production build, 18/18 Chromium/WebKit end-to-end checks,
      2/2 focused integration checks, and 2/2 exact-bundle production smokes.
- [x] Local benchmark candidate passes current accessibility and post-readiness
      no-network checks. Firefox is explicitly unverified on this host because
      launch failed with `spawn UNKNOWN`.
- [x] Genuine physical-reference evidence is recorded: 3 warm-ups + 20 runs,
      p50/p95 `18.78000009059906`/`22.119999885559082` ms, peak
      `45.64192485809326` MiB, and `25,128,921` first-load body bytes; all gates
      pass for the exact reference environment only.

## Privacy, security, and licensing

- [x] No secret, absolute local path, raw dataset, private image, notebook
      output, or unexpected domain appears in the prospective source tree or
      built site. Git-history scanning awaits the first source commit.
- [x] Internal planning, detailed contribution/AI, continuity, and review
      records are excluded; sanitized public authorship, AI-assistance, and
      research-decision disclosures remain.
- [x] Local benchmark candidate has no arbitrary-image upload path and its
      post-readiness browser check sends no image/API request.
- [x] Local-candidate dependency, secret, host-path, and license scans are
      reviewed and clean at their recorded observation time.
- [x] Dataset, checkpoint, dependency, trained-model, example, and asset notices
      agree with the exact 36-file local production bundle.
- [x] Privacy and limitation text is visible and matches the benchmark-only
      product form.

## Public communication and authenticity

- [x] README, cards, results, explorer copy, and demo drafts agree with the
      approved Gate C boundaries for Gate D review.
- [ ] The named maintainer approves contribution/AI-assistance wording.
- [ ] Any public independent-reproduction claim is supported by a separately
      recorded frozen-path reproduction.
- [x] Repository description/topics draft, review preview, one-page brief, and
      `CITATION.cff` match the local candidate. Actual GitHub fields await Gate D.
- [x] No “first,” SOTA, production, clinical, UAE-wide, smartphone, robustness,
      scale-replacement, guaranteed-interval, or realized-impact claim appears
      in the reviewed candidate surfaces.
- [x] The release candidate documents the path-specific cross-platform byte
      contract without changing frozen scientific values or claiming
      applicant-performed independent reproduction.

## Deployment and recovery

- [ ] The named maintainer grants explicit Gate D approval.
- [ ] Release-only workflow deploys the reviewed static archive.
- [ ] Live URL, version, model/evidence hashes, links, examples, keyboard flow,
      privacy, and notices pass a post-deploy audit.
- [ ] `v1.0.0` tag, commit, build ID, archive hash, and rollback artifact are
      recorded.
- [x] Local/recorded-demo fallback decodes successfully; six screenshots and a
      captioned silent walkthrough are hash-manifested for local review. This
      is not evidence of narration or independent reproduction.
- [ ] Weekly smoke workflow is enabled for the supported release period.

## Sign-off

- Machine Gate C recommendation: **benchmark/failure explorer**.
- Gate C evidence/product decision: **Approved 20 September 2026**, as
  a benchmark/failure explorer with the Gate C review memo's claim boundaries.
- Gate D public-release approval for the exact release-candidate commit:
  **Pending in this pre-approval checkout**.
- Release timestamp/tag/commit/URL: **Absent**.
- Contribution wording and any independent-reproduction review: **Pending**.
