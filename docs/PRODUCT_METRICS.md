# Product metrics

PlateGauge intentionally has no production analytics. Product evidence comes
from deterministic automated tests and, only if conducted, a small optional
comprehension study.

## Automated release metrics

| Metric | Definition | Target | Current |
|---|---|---:|---|
| Benchmark explorer flow | Bundled examples, evidence, limitations, and fixed replay harness render correctly | Pass in tested browsers | **Pass:** current Chromium/WebKit journeys |
| Arbitrary-input surface | Upload or unrestricted-estimator control in benchmark-only candidate | Absent | **Pass:** removed |
| Image-network leakage | Image/API requests after fixed-pair readiness | 0 | **Pass:** local browser check |
| Keyboard completion | Entire public explorer flow without pointer | Pass | **Pass:** current browser suite |
| Critical automated accessibility findings | Axe serious/critical findings in tested flow | 0 | **Pass:** current browser suite |
| Reset cleanup | User-image state requiring reset | Not applicable in benchmark-only UI | **N/A:** no arbitrary image input |
| Warm inference latency | Reference laptop browser p95 | ≤1.5 seconds | **Pass:** 22.119999885559082 ms; p50 18.78000009059906 ms |
| Peak application memory | Reference laptop measured peak | ≤512 MB | **Pass:** 45.64192485809326 MiB via `performance.measureUserAgentSpecificMemory` |
| First-load body bytes | No-store response bodies through fixed-pair readiness | Record | **25,128,921 bytes** |
| Availability smoke | Site, model hash, example, and internal links | Pass weekly during cycle | Not deployed |

These metrics establish software behavior, not usefulness in food-service work.
The performance rows apply only to headed Chrome `152.0.7977.83` on the HP
Laptop 15-fd0xxx reference device (i7-1355U, 15.652 GiB, Windows
`10.0.22631`). They do not support phone or unmeasured-browser claims.

## Optional human comprehension metrics

If the optional study runs: supported/unsupported-pair recognition, fraction vs
grams distinction, interval interpretation, abstention action, number of capture
assumptions recalled, and confusion categories. There is no Net Promoter Score,
impact estimate, or invented qualitative quote.

## Prohibited proxy claims

Repository stars, page visits, model invocations, test count, or a polished UI
must not be described as user impact, adoption, accuracy, or research quality.
