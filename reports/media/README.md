# Review media

These images are deterministic review assets captured from the exact local
benchmark/failure-explorer release candidate. They are not evidence of release
approval, a public deployment, a validated estimator, or operational impact.

Generate them while the audited production preview is available locally:

```powershell
cd web
pnpm run capture:portfolio -- --url http://127.0.0.1:4177/plategauge/
```

`portfolio-media-manifest.json` records each file's SHA-256, byte count,
purpose, product boundary, model hash, and static-bundle inventory identity.
The six numbered screenshots implement the frozen review-media plan. The
1280×640 image is the candidate GitHub social preview.

The captioned, silent local walkthrough is generated with
`pnpm --dir web run record:demo`. It is a review and backup artifact—not human
narration, an independent-reproduction record, a deployment, or a public release.

The screenshots contain attributed LeFood-Set v1 example images. Preserve the
repository `NOTICE`, dataset DOI `10.17632/cchsk79jkt.1`, displayed CC BY 4.0
terms, author attribution, and change notice whenever redistributing them.
