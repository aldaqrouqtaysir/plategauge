# Maintenance audit: 23 September 2026

Baseline: `cb3a3b310658eb25d5cf94c0aa118b3ae4446ef2`, with the r3 camera
archive live. The audit checked all 45 live files against that archive before
making source changes. Read-only review preceded implementation.

## Findings and repairs

| Area | Finding | Bounded repair |
| --- | --- | --- |
| Capture ownership | Opening a notice in a new tab cleared unsaved photos in the original tab | Respect modifiers, prevented events and link targets; preserve cleanup on actual departure |
| Keyboard access | Focused capture skip link sat behind the sticky header | Put focused navigation above the header; test painted visibility and its main-content destination |
| Session consistency | The page accepted a mass string longer than the session codec's 64-character limit | Share validation and reject the invalid input before inference or save |
| Failure recovery | The page hid known input and timeout errors behind a generic message | Show only allowlisted recovery guidance; never reflect native error strings or photo data |
| Dependency maintenance | A pip-only update proposal omitted uv.lock and failed locked CI | Use uv-aware updates, retaining locked installation and review |
| Historical operations | Bot proposals rewrote version-specific release workflows | Exclude named frozen workflows; use a reviewed successor for upgrades |
| Documentation | Current-facing links identified r1 as live while r3 was deployed | Centralize current identities, observations and rollback instructions |
| Media tooling | Default output overwrote tracked historical media and used an old fixed date | Require a fresh external output directory and record actual generation time |
| CI coverage | Ordinary CI omitted standalone release-tool checks | Test bounded release-profile discovery, verifier regressions and harness types |
| Scientific utilities | Residual quantile selected an extra order statistic; parity could accept invalid comparisons | Explicit legacy/v2 strategy separation and fail-closed validation; no changed results |
| Export consistency | Generic export used 15 MiB instead of the release gate's decimal 15 MB | Share the canonical 15,000,000-byte ceiling and test its boundaries without changing the model |

The product failures were reproduced using generated inputs in Chromium,
Firefox and WebKit. The camera review layout had no detected horizontal
overflow or axe violations at the audited 320, 768 and 980 pixel widths.
Synthetic checks are not physical-device or accuracy validation.

## Preservation and remaining limitations

No training, new dataset, scientific recalibration, prediction change, model
replacement, expanded accuracy claim or historical-release rewrite accompanies
these repairs. The [research utility erratum](RESEARCH_UTILITY_ERRATA.md)
explains the numerical issue, the preserved legacy default and the prospective
opt-in correction. Reproducing a frozen experiment still requires its original
source revision; maintenance source must not be substituted silently.

PlateGauge has no server-side application backend. Static hosting and local
worker inference remain appropriate to its privacy contract; a backend would
not resolve the main evidence gap. The paired model still did not outperform
after-only in the frozen benchmark, and real-camera accuracy, physical-device
reliability and operational benefit remain unvalidated.

Historical artifacts and failed checks remain retained. Final delivery identity
and actual hosted outcomes belong in [Current release](CURRENT_RELEASE.md),
not in an assumption that source tests automatically publish a website.
See [Maintenance](MAINTENANCE.md) for safe future update and media procedures.
