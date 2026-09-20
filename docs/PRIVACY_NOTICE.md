# PlateGauge privacy notice

## What the explorer processes

PlateGauge is a static benchmark and failure explorer. It does not accept image
uploads, camera input, user-supplied mass, accounts, or free text. The images
shown in the explorer are fixed examples from LeFood-Set v1, bundled with the
application under the dataset's CC BY 4.0 terms. They are research evidence,
not images supplied by a visitor.

The explorer has no PlateGauge application server, database, analytics,
advertising tracker, cookie, telemetry service, or prediction-history feature.
It does not create or transmit a per-user prediction because it provides no
custom-input prediction workflow.

## Fixed-pair benchmark harness

The benchmark route can load one bundled image pair, the same-origin ONNX
model, and its WebAssembly runtime to test artifact integrity and replay browser
inference. The route accepts no custom files. It suppresses and does not retain
the model's numeric output, and its training-set replay is not evaluation
evidence.

## Network and hosting boundary

Release builds are required to pass an automated production-route test that
permits only an enumerated set of same-origin static assets and rejects
unexpected image or API traffic. The built-site inventory also rejects remote
runtime assets, raw data, unknown files, source maps, high-confidence secrets,
and build-host paths.

When the site is served through GitHub Pages, GitHub, the visitor's browser,
internet provider, employer or school network, device software, or browser
extensions may process ordinary request metadata while loading the page and
assets. PlateGauge does not control those parties and does not promise
anonymous browsing.

## Superseded estimator design

> **Historical design only.** Earlier plans described selecting personal
> before and after food images for local browser inference. The frozen product
> gates did not support that estimator, so this interface contains no such
> input. Reintroducing custom input would require a separately evaluated scope,
> renewed privacy and security review, and updated tests and notice.

Security concerns should be reported using the process in `SECURITY.md`. Do
not attach sensitive or identifying images to a report.
