# Monitoring/documentation correction — local candidate

This replacement candidate is local-only, not published or deployed. Its parent
was published to PR 10 for checks but did not advance main. It changes monitoring
and reference documentation only. The live application remains immutable v1.0.2, using the
unchanged v1.0.0 model. Publication needs separate approval of the exact source.
There is no new app version, model, scientific result or application-use approval.

## Observed failure, preserved

The [first weekly run](https://github.com/aldaqrouqtaysir/plategauge/actions/runs/35583108195)
passed the public page/model checks, comparisons of 25 tracked public files,
fixed-model replay and observation-artifact upload. Its documentation step failed.
The broad Markdown glob ran after dependencies were installed: 755 reported
errors and 37 timeouts belonged to dependency documentation. Two project-owned
prior-art references returned HTTP 403 (MDPI) and HTTP 404 (Winnow's old path).
Neither those failures nor the preceding failed release history is waived.

## Correction

- Two independent jobs distinguish live-application failures from documentation
  and external-reference failures. Neither has `continue-on-error` or depends on
  the other. The whole workflow still fails if either job fails.
- The live job keeps checking the immutable v1.0.2 tag. Its URL validation,
  checksum, byte comparisons and genuine fixed replay remain unchanged; requests,
  steps and the job have explicit time bounds.
- The documentation job checks the workflow's current source, without installing
  application dependencies. It enumerates Git-tracked Markdown into an explicit
  file list. Dependencies/generated outputs and untracked files cannot expand it.
  Inputs must be existing, non-symlinked, unambiguous project-relative files.
  Empty input sets, path escapes, glob/URL syntax and stale diagnostics fail.
- Lychee remains pinned to 0.24.2 and the existing action commit. There is no
  persistent disk cache, insecure TLS, ignored publisher domain or blanket acceptance of
  403/404/429. Only HTTP 200 is accepted (local-file success is also supported).
  Requests allow 15 seconds, one retry, four concurrent requests, two per host,
  and five redirects. The checker step is bounded to five minutes.
  The reported `cached` counter can include reuse of repeated URLs within the
  current run; it is preserved, not incorrectly treated as stale disk evidence.
- Preserve input paths/hashes, raw JSON and classified findings outside source
  for 90 days, including on failure. Missing/malformed/empty reports or nonzero
  checker exits cannot become a success. Blocked/rate-limited references remain
  unresolved failures, separately identified from missing references/timeouts.
- Network-free synthetic regressions run in the existing Python suite and a
  dedicated Windows/Linux CI job. The parent ran in authorized hosted CI with
  the setup failure recorded below. Hosted execution of this replacement still
  requires authorization; local tests do not establish hosted success.

## Windows runtime correction (21 September 2026)

Parent `8aea30b87386a0d0fb7d64752ddf4d45b0b8eeea` was submitted as
[PR 10](https://github.com/aldaqrouqtaysir/plategauge/pull/10).
[CI run 35592005024](https://github.com/aldaqrouqtaysir/plategauge/actions/runs/35592005024)
finished with nine passing jobs and one failed job. The new Windows job requested
Python 3.12.14 directly from setup-python, which could not supply that version
for Windows 2025. Its tests never executed. Main was not advanced; the revised
weekly monitor was not dispatched. Neither failure is waived.

This local-only amendment reuses the existing passing Windows portability job's
bootstrap pattern: setup-python supplies 3.12.10 on Windows (3.12.14 on Linux),
pinned uv 0.12.17 installs managed 3.12.14, and an explicit version assertion
precedes the tests. Runtime acquisition may use networking; the test command
uses uv's offline mode, no project/config discovery and a required managed
interpreter. Only the runtime manager is installed: no project dependencies,
training extras, project synchronization or model execution are part of this job.
The five-minute limit and strict failure behavior remain.

The workflow-contract regression rejects the historical Windows setup and
mutations that bypass version checks, remove isolation/offline flags, unpin the
runtime manager, install project dependencies, relax the timeout or suppress
failure. The local review previously missed runtime acquisition because its
Windows tests used an already-installed interpreter. This correction does not
claim to have reproduced a clean GitHub runner locally; hosted verification of
the exact replacement remains a separate approval and evidence step.

Only the monitoring CI setup, its contract tests and this correction record
change relative to the parent. The weekly workflow and monitoring implementation
are byte-identical to that parent. Scientific values and bound evidence are
unchanged. No release tag, app version or authority flag changes.

## Reference decisions (checked 21 September 2026)

The Winnow link now uses its [official site](https://www.winnowsolutions.com/),
which identifies Winnow Vision and describes its camera/scale workflow. Only
the prior-art table's URL changed; no product-impact or superiority claim was added.

The FLIC citation is still the same MDPI article, DOI `10.3390/app16115465`.
Publisher and author-institution metadata identify the same article. Automated
requests to the publisher and institutional landing-page alternatives were
blocked. The existing publisher citation is retained: replacing it with another
blocked endpoint, dropping the reference, or accepting 403 would not fix access.
This remains an external-access limitation, not proof the paper is missing.
No FLIC dataset was used, and the dataset-exclusion decision is unchanged.

The reference job can therefore still fail on the publisher restriction. A green
application check must never be presented as a green external-reference check.
External responses can vary across local/hosted networks; preserve both outcomes.

## Scope and authenticity

Implementation, diagnosis, synthetic testing and documentation were AI-assisted.
The applicant approved this bounded correction; no applicant-performed testing,
technical mastery or independent reproduction is asserted. Scientific files,
model/manifest bytes, examples, results, claims and all existing tags remain fixed.
The previous public assistance disclosure is unchanged. Private v2 remains private.

No production traffic, visitor data, new research evaluation, training, calibration,
application material, remote workflow dispatch or deployment is authorized here.
Before publication, review the exact commit, allowlisted diff and test evidence.
After a separately authorized source publication, run the new read-only workflow
once and record both job results. Do not redeploy the app or move a release tag.
