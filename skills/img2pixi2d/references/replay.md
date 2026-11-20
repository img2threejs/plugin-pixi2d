# Isolated ESM replay — evidence only, not native-node authority

`tools/replay-pixi2d.mjs` executes a frozen, explicitly adapted scene in a fresh,
program-owned Chromium process/profile and captures its **actual viewport via CDP
from outside the page**. It does not use a user tab or page-controlled
`canvas.toDataURL`. It never changes the reviewed snapshot, capture, evidence,
review or artifact files. It installs/downloads nothing and makes no model call.

**Every successful result and capture declares**
`nativeNodeProvenance: "unevaluated"` and `terminalAcceptance: false`.
The arbitrary entry/behavior JavaScript shares mutable Pixi/browser objects with
the host. External screenshots and exact byte pins do not exclude renderer
mutation, fabricated node identities or raster overlays. Neither this replay,
`matchesSavedCapture: true`, an authenticated semantic review, nor the plugin gate
can clear the base's `terminal-native-capture-authority-unavailable` blocker.
This is useful replay/capture evidence, not a stronger confinement claim.

## Explicit frozen source ABI

Add this **before producing the new snapshot and review** to `inputs.json`:

```json
"replay": {
  "abi": "img2.routed-pixi-scene/v1",
  "entry": "src/route-entry.mjs",
  "modules": ["src/route-entry.mjs", "src/actual-subject.mjs"],
  "assets": [{"path": "art/owner.png", "alias": "owner", "type": "texture"}]
}
```

Every module must be an exact bound editable source. The entry must appear in
`modules`. This list is the complete permitted browser-executable module closure;
relative imports and `pixi.js` are supported, and every served module is pinned by
its actual bytes. Runtime imports outside the declared closure fail. Runtime
asset paths must appear in the ordinary bound `assets` manifest. Aliases are
unique. Loader types are `texture` (actual Pixi Assets load), `font` (actual
FontFace, with alias as family), `json`, and `bytes` (Uint8Array). Licences and
provenance remain bound resources but need not be runtime-loaded.

The entry exports:

```js
export async function createRoutedPixiScene({ app, PIXI, assets }) {
  // Call the actual delivered factory, using its real loaded resources.
  const scene = createActualSubject(app.stage, { ownerTexture: assets.owner });
  return {
    root: scene.root,
    nodes: scene.nodes,
    behaviors: actualRequestedRunAndResetCallbacks,
    dispose: () => scene.dispose(),
  };
}
```

This is an interface example, not an implementation of missing behavior.
`root` must be the real native scene Container, unattached or attached directly
to the fixed host stage. `nodes` is the delivered Map/object of independent named
nodes. `behaviors` maps **every** frozen `behaviorChecks` id, including lifecycle,
to real `{run, reset}` callbacks against that same scene. Do not use no-ops to
satisfy lifecycle/motion, generate replacement geometry, or rasterize the whole
reference into an imitation. The existing factory must preserve its actual
subject, requested behavior and permitted assets. Missing adapters, exports,
modules, fonts, callbacks or resources block; none is inferred or substituted.

`profile.json` must explicitly specify:

```json
{"width":64,"height":64,"renderer":"webgl","resolution":1,
 "antialias":false,"background":0,"backgroundAlpha":0}
```

Use the actual requested artboard/settings, not this example's size. Other
renderer/resolution conventions require a separately approved host adapter and
are refused, never silently rescaled. Browser-native `.js`/`.mjs` ESM is required.
TypeScript, TSX, CJS, host framework bootstraps, arbitrary package imports and
project builds are **not** transpiled, executed through Node, or replaced. An
existing TS/host-specific factory without a faithful explicit ESM adapter is an
exact prerequisite blocker. If the user's existing build already produces the
real browser modules, bind those exact modules as editable sources alongside the
authored source, then implement the adapter against that actual output. Never
claim that this tool proves a source-to-build equivalence it did not measure.

The program-owned host creates the pinned Pixi Application, loads declared
assets, imports the entry, mounts its returned root and runs the existing native
node/edit/reset probes and actual callbacks. It freezes no requested behavior
into a substitute picture. Unrelated animation must not run during deterministic
captures; the source must support the declared seek/reset states. The producer
checks each requested edit changes the external screenshot and each reset returns
to baseline. This is still not semantic/motion-cycle acceptance.

## Runtime prerequisites and held pins

Provide already installed, read-only prerequisites:

- Node ≥20, matching the host CPU (an x64 Node may launch universal macOS Chrome
  under Rosetta; use an already installed arm64 Node on Apple Silicon).
- Exact PixiJS **8.22.0**, including its official `unsafe-eval` CSP-compatibility
  bundle. This module uses static shader/uniform sync implementations; CSP
  `unsafe-eval` is **not** enabled.
- Exact Playwright and playwright-core **1.64.0**.
- An existing Chromium executable and its complete bundle directory.

The runtime lock pins Node bytes/version, OS/architecture, the complete Pixi,
Playwright/core and Chromium file trees, and this plugin's driver, fixed host and
capture-helper bytes. Symlinks cannot escape each pinned runtime root. The held
lock must be outside the scene workspace and independently inspected/approved;
generating a lock is only measurement, not approval or installation.

Use these same explicit arguments for every command, replacing paths with the
real already-installed prerequisites:

```sh
node "$SKILL_DIR/tools/replay-pixi2d.mjs" pins \
  --pixi-package /approved/node_modules/pixi.js \
  --playwright-package /approved/node_modules/playwright \
  --chromium /approved/ChromiumExecutable --chromium-root /approved/ChromiumBundle
```

Save the emitted lock outside the workspace through the caller's approved file
channel. Then obtain initial capture evidence on stdout:

```sh
node "$SKILL_DIR/tools/replay-pixi2d.mjs" capture --workspace "$PWD" \
  --runtime-lock /approved/held-lock.json \
  --pixi-package /approved/node_modules/pixi.js \
  --playwright-package /approved/node_modules/playwright \
  --chromium /approved/ChromiumExecutable --chromium-root /approved/ChromiumBundle
```

The caller may save **only the actual `replayCapture` object** as its new
`capture.json`, then use the ordinary `produce` and native semantic review flow.
The driver itself never overwrites a reviewed artifact. With existing candidate
`capture.json` and `artifact.json`, use the identical argv with command `replay`
instead of `capture`. This re-executes the frozen source in a new owned browser,
rehashes bound inputs/runtime after capture, and reports exact comparison without
changing either candidate record.

Requests are fulfilled only from immutable, bound source/asset buffers and exact
pinned program modules at an isolated loopback origin. Every other request,
WebSocket or popup is refused. CSP blocks arbitrary scripts/eval/workers/frames;
the driver also uses disabled background services, a dead external proxy and
DNS denial. Chromium's sandbox stays enabled; no existing browser endpoint or
profile is accepted. Effective browser arguments and actually loaded resource
hashes are reported separately from the allowlist.

## Result contract

One JSON envelope on stdout, exit 0 for a completed diagnostic replay or 2 for a
blocked replay. `img2.pixi2d-live-replay` v1 includes:

- `objectId`, canonical `snapshotSha256`, raw-file `snapshotBinding`.
- `captureBinding` and `artifactBinding`: exact workspace-relative saved file
  paths and raw byte hashes (`null` for initial `capture`).
- `replayCapture`: actual external-CDP PNG data with the normal capture fields,
  producer `pixi2d-cdp-replay-v1`, plus both mandatory non-authority fields.
- `replayCaptureSha256`: SHA256 of **canonical JSON**, not the saved file's raw hash.
- `matchesSavedCapture`: canonical equality with the parsed saved capture, or null
  for initial capture. False is a diagnostic mismatch, never permission to rewrite
  the reviewed evidence.
- Exact `sourceBindings`, `assetBindings`, runtime tree pins,
  `runtimeLockSha256`, `browserVersion`, effective `browserCommandLine`,
  `renderedHostSha256`, allowed module hashes and actual `loadedResources` hashes.

Blocked results include reasons and the same explicit non-authority fields.
No result is a gate pass, human review, quality score or canonical action.

## Real-source regression fixture and remaining authority gap

`tests/fixtures/routed-scene.mjs` and `shape.mjs` construct real native Pixi
Graphics, exercise independent edits, and actually dispose/recreate while
preserving a shared Texture consumer. They are technical regression fixtures,
not a user's reconstruction, original reference or quality benchmark.

Set `IMG2_TEST_HARNESS` and `PIXI_REPLAY_RUNTIME` (JSON with `pixi-package`,
`playwright-package`, `chromium`, `chromium-root`) to approved installed paths.
Then, after all writers finish, the verifier can run:

```sh
python3 -m unittest discover -s tests -p test_replay_runtime.py -v
node --test tests/review-capture.test.mjs
```

The focused runtime-reproduction entrypoint is
`python3 tests/test_replay_runtime.py --reproduce`; it is not a test-suite or
visual-quality pass. Absent prerequisites are explicitly skipped by the suite;
the reproduction refuses without them. No mock-browser fallback exists.

A future terminal authority still needs an independently confined/native-node
verifier that owns the actual rendering primitives, cannot be monkey-patched by
source/callback code, and proves the exact bound scene graph generated each
captured pixel/state. It must preserve the delivered source/host behavior rather
than quietly replace it with a limited data graph, bind the full executable and
asset closure, verify real edit/reset/lifecycle effects, recapture/review changed
bytes, and run live from the base's reviewed command with independently held pins.
Until that boundary is genuinely implemented and reviewed, terminal acceptance
remains blocked even when these diagnostic screenshots match perfectly.
