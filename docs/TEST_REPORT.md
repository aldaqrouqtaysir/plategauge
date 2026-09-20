# Test report

> **Source-freeze status on 20 September 2026:** frozen research evidence,
> consolidated software QA, and the local release-candidate audit were complete.
> The audit recorded `technicalStatus=passed`, no failed checks, and
> `releaseReadiness=blocked_pending_gate_d_actions`. At that point Gate D,
> source commit, tag, remote, deployment, and live public smoke evidence were
> absent. Any later release status must be verified from its commit-bound
> approval, manifest, deployment, and public-smoke records.

## Frozen evidence validation

| Check | Required invariant | Verified result |
|---|---|---|
| Data audit | ≥500 valid pairs; exact hashes; duplicate/category containment | **Pass:** 514 pairs, 34 categories, 103/103/103/103/102 folds, zero cross-fold duplicate component, `issues=[]` |
| Protocol preflight | Exact config/folds/manifest/audit identities | **Pass:** protocol `9450069d…73e8f` |
| Confirmatory run | Validated inner selections before opening each outer task | **Pass:** clean run `f1c7cfd…eda4`; M2 selected in all five folds |
| Outer coverage | Every valid row exactly once per workload | **Pass:** 514 rows for each of eight workloads |
| Final selection | Modal configuration and median selected epoch | **Pass:** M2, epoch 6 |
| Aggregate analysis | Immutable predictions; frozen metrics/gates/statistics | **Pass:** `results.json` and `bootstrap_comparisons.json` generated and hash-bound |
| Same-category diagnostic | Isolated runner; duplicate-safe split; 511-row matched estimand | **Pass:** five diagnostic tasks and immutable summary |
| Error analysis | 514 unique primary predictions; top/bottom 20 | **Pass:** immutable ranking plus separate annotations |
| Label sensitivity | Post hoc only; cannot alter frozen result | **Pass:** four-row exclusion leaves paired worse; `changes_frozen_results=false` |
| Robustness | 514 rows × 17 conditions; frozen downgrade rule | **Pass as analysis:** one routine breach; robustness downgrade required |
| Export binding | Checkpoint/final selection/run/protocol/data/ONNX cross-bound | **Pass:** sidecar `status=passed` |
| ONNX parity | Maximum drift ≤`1e-4` | **Pass:** `5.185604095458984e-06` over eight frozen samples |
| Model size | FP32 ONNX ≤15,000,000 bytes | **Pass:** 10,355,122 bytes |
| Physical browser | Warm p95 ≤1,500 ms; peak app memory ≤512 MiB | **Pass:** headed Chrome `152.0.7977.83`, p95 `22.119999885559082` ms, peak `45.64192485809326` MiB; 3 warm-ups + 20 measurements |

## Consolidated software verification

The consolidated verification for the source-frozen local release candidate
recorded:

- **209 Python tests passed and 1 intentional skip**;
- **85.51% coverage for the configured non-training Python scope**; this
  measurement excludes `model.py`, `training.py`, and `export.py` as declared
  in `pyproject.toml`, so it is not whole-repository or training-code coverage;
- Ruff clean;
- strict mypy clean;
- ESLint clean and strict TypeScript clean;
- **79 Vitest tests passed**;
- production build passed;
- **18/18 Chromium/WebKit Playwright end-to-end checks passed**, including axe
  accessibility and post-readiness no-network checks;
- **2/2 focused integration checks** and **2/2 exact-bundle production smokes**
  passed against the benchmark workflow, with the production source URL fixed
  by the test configuration;
- an unlinked `?benchmark=1` timing harness bound to fixed sample
  `lefood-0192`; it never renders or retains the all-data model's numeric
  prediction; and
- the Firefox binary could not launch on this Windows host before tests ran;
  Firefox remains in CI, and no local Firefox pass is claimed.

At source freeze, the live public smoke test was intentionally blocked because
there was no approved deployment or configured public URL. That is distinct
from the two local production-smoke checks against the built static candidate,
which both passed.

## Local release-candidate checks

The public technical records in `reports/release/static-bundle-audit.json`,
`reports/release/production-smoke-observation.json`, and the generated
browser-evidence verification record support:

- an exact **36-file** production bundle with reviewed hashes, notices,
  examples, and same-origin assets;
- a fail-closed generated browser-evidence payload binding ten displayed
  examples and every visible benchmark value to 18 canonical frozen sources;
- a benchmark-only interface with ten fixed records, no arbitrary-image input,
  and no rendered live numeric model output;
- **2/2** local production-smoke checks passed, with full-navigation requests
  restricted to allowlisted same-origin `GET` assets;
- clean high-confidence secret and host-path scans and no raw workbook/archive
  or unapproved image in the candidate tree;
- network-refreshed, hash-bound Python and JavaScript dependency/license
  observations with no known advisories at the observation time; and
- release workflow guards that fail closed without an approved tag, approval
  record, protected environment, and explicit deployed URL.

These are local technical results, not release authority or evidence that a
public deployment exists.

## Environment and security snapshot

- Windows local workspace; Python 3.12.14; Node 24.19.0; pnpm 11.19.0; uv
  0.12.17.
- At source freeze no release commit/tag existed; the working tree was not a
  published release.
- The 20 September network-refreshed Python and full/production JavaScript
  audits reported no known vulnerabilities at observation time. The local
  editable PlateGauge distribution was the one documented Python audit skip.
- Hash-bound Python and production-JavaScript license inventories are recorded
  in `reports/security/`; their observations are time-sensitive and the release
  workflow must refresh them for the approved tagged build.
- Heuristic high-confidence local secret and host-path scans passed. A
  history-wide scan requires the later source commit and release workflow.

## Pending Gate D actions at source freeze

The technical audit listed only authorization or release-infrastructure work as
pending:

- Gate D approval plus independent frozen-path reproduction and
  contribution-language sign-off;
- source commit, `v1.0.0` tag, remote, and required-reviewer GitHub Pages
  environment;
- a release-workflow refresh of time-sensitive scans against the approved tag;
- deployment followed by a live public smoke test against the explicit URL;
  and
- Firefox evidence only on a host where Firefox can launch—never inferred from
  Chromium or WebKit.

At source freeze, no Gate D action above had occurred. If a release is later
made, its approval record, release manifest, and public-smoke observation—not
this snapshot—are authoritative for the new state.

The browser performance evidence is complete for one measured environment only:
headed Chrome `152.0.7977.83` on HP Laptop 15-fd0xxx, i7-1355U, 15.652 GiB,
Windows `10.0.22631`. First-load body bytes were `25,128,921`; nearest-rank warm
p50/p95 were `18.78000009059906`/`22.119999885559082` ms; peak application
memory was `45.64192485809326` MiB via
`performance.measureUserAgentSpecificMemory`. No phone or unmeasured-browser
performance claim is supported.
