# PlateGauge 1.0.2: release-diagnostic isolation candidate

This is an unapproved-source maintenance candidate. An isolated verification
branch/PR may run tests; it cannot advance public main, create release approval
or a tag, deploy, or expand scientific claims. Both published tags remain fixed.

## Observed release-only failure

The approved v1.0.1 source was published, but
[release run 35572180961](https://github.com/aldaqrouqtaysir/plategauge/actions/runs/35572180961)
stopped before deployment. Its generated dependency-license inventory lived at
`release-scan-artifacts/node-licenses.json` inside the checkout. The prospective
source scanner included that untracked report and detected runner-local paths.
The report was diagnostic output, not intended source. No secret was found.

Approval/evidence verification, audits, 92 web unit cases, 33 browser cases,
two ONNX integration cases, static build, Ruff and mypy passed. Python reported
215 passed, one failed, one intentional skip, and 85.57% coverage. Later release
steps were not run. Passing candidate CI had not reproduced this exact ordering.

## Narrow correction

- Create a fresh, job-scoped directory below runner temporary storage and
  outside source for CI/release vulnerability, license and secret-scan reports.
  Reject in-source destinations, path-bearing identifiers and stale directories.
- Keep the source-hygiene scanner, full-history secret scan, coverage floor,
  dependency gates and scientific checks. No new ignore rule hides diagnostics.
  Synthetic regressions prove accidental in-source reports and genuine
  tracked/untracked leakage are still detected.
- Share the full engineering sequence in
  `.github/actions/release-checks/action.yml`: fresh audits, browser checks,
  build, full Python checks, static allowlist/notices, production smoke and
  packaged model/manifest byte checks. CI rehearses the same action with only
  read permission and no Pages configuration/deployment steps.
- The real release first checks the approval-only parent relation, runs that
  shared action, verifies the committed approval and bound evidence, and only
  then packages for protected Pages deployment. The isolated rehearsal contains
  no approval record. Synthetic approval records exist only in temporary tests.
- Preserve scan and browser failure diagnostics as action artifacts. Preserve
  a successful rehearsed dist with a name that explicitly does not imply
  release approval. Actual approved rollback artifacts still require the real
  committed-approval check.
- Identify software/citation as 1.0.2 and retain the exact v1.0.0 model manifest.
  Extend only the explicit release/model mapping; arbitrary versions stay blocked.

The prior local audit's pending text is made conditional on its actual scope:
it never grants approval and does not determine remote/deployment state.
Its authority flags and the real verifier remain separate and fail closed.

## Verification contract

Before proposing publication: clean Windows and LF checkout tests, synthetic
diagnostic/source-boundary regressions, synthetic approval/tamper tests, full
local checks, native hosted Linux/Windows checks and the shared release-order
rehearsal must pass. Run counts belong to the review tied to the exact candidate
commit; this document is not a prediction of passing results.

No model or research fitting occurs except the previously allowlisted synthetic
regression unit tests, with no saved research model or scientific claim.
Datasets, splits, golden files, weights, predictions, metrics, public example
assets, scientific cards and bound evidence remain unchanged. No custom inputs,
private v2 materials, independent-reproduction claim or application use is added.

Live deployment, live byte comparisons, live inference and weekly monitoring
are not established by a local/CI rehearsal. After separate approval of the
exact successor commit, the unchanged release gates must pass before deployment;
restore the homepage and enable weekly monitoring only after live verification.
