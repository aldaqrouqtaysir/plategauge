# Accessibility review

**Source-freeze snapshot (20 September 2026):** automated local review was
complete for the Gate C-approved static benchmark/failure explorer. Manual
assistive-technology validation remained limited; Gate D approval and public
deployment had not occurred at this checkpoint.

## Current-interface requirements

- Semantic heading order, landmarks, navigation labels, buttons, and native
  controls where possible.
- Fixed-example selection and page navigation operable by keyboard, with
  visible focus and logical order.
- Bundled before/after example images have purpose-oriented alternative text;
  filenames are not the only distinction.
- Selected-example changes remain understandable without unexpected focus
  movement.
- Aggregate values, recorded targets, frozen predictions, errors, comparison
  direction, and failed gates do not rely on color alone.
- The “representative success” and “largest error” selection rules are stated
  in text so the example gallery is not mistaken for a random sample.
- Layout remains usable at a narrow 320 CSS-pixel viewport and under browser
  zoom/reflow.
- Contrast targets WCAG 2.2 AA for text and interactive components.
- Motion is nonessential and respects reduced-motion preference.
- Study limitations, attribution, and privacy language are reachable without
  first running a model or providing data.

The current interface has no file input, custom-image preview, mass field,
fresh result, empirical interval, or abstention message. Accessibility claims
must describe the explorer that exists, not the superseded estimator design.

## Verification evidence

| Check | Evidence | Status |
|---|---|---|
| Axe scan of the static explorer | Playwright Chromium/WebKit journeys | **Passed locally:** no automatically detectable serious violations in the tested state |
| Keyboard selection of fixed examples | Playwright narrow-viewport journey | **Passed locally** |
| 320 px responsive layout | Playwright narrow-viewport journey | **Passed locally** |
| Text alternatives and non-color interpretation | Component/browser assertions plus UI review | **Passed for the tested fixed-example and metric views** |
| Production build in Chromium and WebKit | Consolidated browser suite | **Passed locally:** 18/18 Chromium/WebKit checks, including 320 px navigation/text-floor, radiogroup keyboard behavior, live announcement, axe, and no-network coverage |
| Screen-reader smoke with a desktop reader | Manual notes/version | **Pending; no screen-reader usability claim** |
| Firefox launch | Local host attempt | **Binary could not launch before tests ran; Firefox remains in CI, and no local Firefox pass is claimed** |
| Public-site accessibility smoke | Deployed build | **Not run: no deployment or Gate D approval** |

Passing automated Axe checks does not establish accessibility for all disabled
people, all assistive technologies, or all browsers. No blind/low-vision user
validation has been conducted.

## Superseded pre-outcome checklist

> **Historical design only.** Earlier requirements covered accessible file
> selection, input errors, loading/cancel states, numeric results, intervals,
> abstention, and focus restoration after inference/reset. Those controls remain
> relevant only to retained low-level tests or a separately approved future
> estimator; they are not current visitor states.
