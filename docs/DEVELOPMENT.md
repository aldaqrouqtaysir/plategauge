# Local development and focused verification

PlateGauge has two build profiles. The live site uses the experimental camera
profile; the default development/build commands below use the historical
benchmark profile. For the live experience, use the
[camera build guide](CAMERA_CANDIDATE_BUILD.md) after the pinned-tool setup below.
Neither path downloads raw LeFood data or trains a model. To review without
installing tools, use the [reviewer quickstart](REVIEWER_QUICKSTART.md).
See [current release status](CURRENT_RELEASE.md) for exact published identities.

Use the public repository, not a private research checkout. Keep its committed
notices, examples, model and evidence files intact. The existing model is included
for the bounded verification path; no model fitting is part of this guide.

## Pinned tools and checkout

The [CI workflow](../.github/workflows/ci.yml) uses Node.js **22.20.0**, pnpm
**11.19.0**, and, for Python checks, managed Python **3.12.14** with uv **0.12.17**.
Install Node.js 22.20.0 and Git first. The following commands install the pinned
package manager and acquire the public source; these setup steps require network
access and write local software/dependency files.

```text
node --version
npm install --global pnpm@11.19.0
pnpm --version
git clone https://github.com/aldaqrouqtaysir/plategauge.git
cd plategauge
git rev-parse HEAD
git status --short
```

Check that the version output matches the pins. Record the commit you test and
any local changes; an uncommitted checkout is not an exact published-source
reproduction. Do not substitute a tag or claim release approval merely because
a local build succeeds.

## Benchmark browser development

From the repository root:

```text
cd web
pnpm install --frozen-lockfile
pnpm dev --host 127.0.0.1 --port 5173 --strictPort
```

Open `http://127.0.0.1:5173/plategauge/`. Stop the server with Ctrl+C before
starting browser test servers. The development lifecycle prepares the bundled
ONNX Runtime and legal notices in `web/public/ort` and `web/public/legal`.
Missing required source notices are build errors; do not remove the copy step
or skip checks to get past them. No raw dataset or Python installation is needed
for this browser-only path.

From `web/`, run the regular checks:

```text
pnpm lint
pnpm typecheck
pnpm test:unit
```

### Browser tests

The browser installation step downloads test runtimes, not research data:

```text
pnpm exec playwright install chromium firefox webkit
pnpm test:e2e
pnpm test:integration
```

On a clean Linux machine, CI uses
`pnpm exec playwright install --with-deps chromium firefox webkit` to install
required operating-system libraries as well. That may require elevated system
permissions. Use supported installed runtimes; do not disable security or privacy
assertions to work around a missing browser.

If the default local Firefox cache cannot launch, both the baseline and camera
test configurations accept `PLATEGAUGE_FIREFOX_EXECUTABLE` pointing to an
independently verified copy of the **same Playwright Firefox revision**. Record
the override and failed attempt; do not substitute an unrelated browser version.
CI leaves this override unset and uses its locked installation.

The end-to-end configuration serves test mode on port 4173 and uses a test-model
response. The separate integration configuration serves port 4174 with a
committed synthetic ONNX fixture to exercise the real inference code path.
Neither is a food-accuracy evaluation. Do not leave an unrelated development
server on those ports and mistake a test against it for the intended run.

### Build and test the local production bundle

Production builds require `VITE_SOURCE_URL`. Use the exact committed source
identity, not a moving `main` URL. Keep `VITE_PLATEGAUGE_TEST_MODEL` unset;
production configuration rejects it. Keep the default `/plategauge/` base path
for the production tests below.

PowerShell, from `web/`:

```powershell
$env:VITE_SOURCE_URL = "https://github.com/aldaqrouqtaysir/plategauge/tree/$(git rev-parse HEAD)"
pnpm build
$env:PLATEGAUGE_EXPECTED_SOURCE_URL = $env:VITE_SOURCE_URL
pnpm test:production
pnpm preview --host 127.0.0.1 --port 4175 --strictPort
```

Bash, from `web/`:

```bash
export VITE_SOURCE_URL="https://github.com/aldaqrouqtaysir/plategauge/tree/$(git rev-parse HEAD)"
pnpm build
export PLATEGAUGE_EXPECTED_SOURCE_URL="$VITE_SOURCE_URL"
pnpm test:production
pnpm preview --host 127.0.0.1 --port 4175 --strictPort
```

The production test starts its own local preview server. The final command is
for manual inspection after that test finishes; open
`http://127.0.0.1:4175/plategauge/`. This test checks the actual built bundle and
its fixed-example model replay, not custom-photo validity or field performance.
Building and previewing do not deploy anything. Public deployment remains
governed by the [release procedure](DEPLOYMENT.md).

## Camera build and verification

From a clean public checkout with the pinned tools installed, follow the
[camera build guide](CAMERA_CANDIDATE_BUILD.md). Its `build:camera` command
produces `dist-camera/`; `preview:camera` serves the capture-first experience
at `http://127.0.0.1:4192/plategauge/`. The camera browser tests use generated
frames, not physical hardware or model-accuracy ground truth.

Source builds are development artifacts. The live release delivers an exact,
previously verified ZIP; a new build can differ in bytes across platforms.
Changes on `main` and local builds do not deploy automatically.

## Optional Python checks without training

Run these from the repository root, in a terminal with an existing Python/pip
installation. Setup may download the pinned runtime manager and Python runtime:

```text
python -m pip install --disable-pip-version-check uv==0.12.17
uv python install 3.12.14
uv run --no-project --no-config --offline --python 3.12.14 --managed-python python -c "import sys; assert sys.version_info[:3] == (3, 12, 14)"
uv run --no-project --no-config --offline --python 3.12.14 --managed-python python -m unittest discover -s tests/python -p test_monitor_documentation.py -v
```

The last command runs only synthetic, network-free monitoring regressions using
the standard library and temporary Git repositories. It does not load a model,
inspect the dataset, or fit anything. This is a focused check, not a substitute
for the complete CI suite.

For the separate, read-only verification of committed browser evidence, install
the locked core Python environment, without training/export extras:

```text
uv sync --locked --python 3.12.14 --managed-python
uv run --locked python scripts/verify_web_benchmark_evidence.py verify --repo-root .
```

This verifies the browser evidence against committed reports, manifests and
packaged examples. It requires no raw-data acquisition or retraining. Use
`verify`, not `generate`: a mismatch is a failure to investigate, not permission
to regenerate frozen evidence. This check is distinct from independent
reproduction of the research experiment.

## Interpreting results

The [CI workflow](../.github/workflows/ci.yml) and
[shared release checks](../.github/actions/release-checks/action.yml) define the
broader engineering sequence. Passing the scoped commands above does not imply
that every CI, vulnerability, licensing, release or live-site check passed.
Retain failures and identify the exact command, source revision and environment
when reporting them. Do not rewrite historical test counts after a new run.

Release-operations tests, safe media authoring and dependency-update boundaries
are covered in the [maintenance guide](MAINTENANCE.md). Historical recording
commands require a fresh explicit external output; they are not a way to replace
the published screenshots or demo in place.

Keep generated diagnostics outside tracked source and do not publish personal
paths, images or private research material. See [CONTRIBUTING](../CONTRIBUTING.md),
[security reporting](../SECURITY.md) and the
[cross-platform evidence-byte contract](REPRODUCIBILITY_NOTE.md).
