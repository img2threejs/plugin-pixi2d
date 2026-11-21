# Isolated ESM replay and explicitly reviewed capture authority

`tools/replay-pixi2d.mjs` executes a frozen, explicitly adapted scene in a fresh,
program-owned Chromium process/profile and captures its **actual viewport via CDP
from outside the page**. It does not use a user tab or page-controlled
`canvas.toDataURL`. It never changes the reviewed snapshot, capture, evidence,
review or artifact files. It installs/downloads nothing and makes no model call.

Ordinary `capture`/`replay` results and captures declare
`nativeNodeProvenance: "unevaluated"` and `terminalAcceptance: false`.
Arbitrary entry/behavior JavaScript shares mutable Pixi/browser objects with
the host. External screenshots and exact byte pins do not exclude renderer
mutation, fabricated node identities or raster overlays. Diagnostic replay,
`matchesSavedCapture: true`, semantic review and the plugin gate alone cannot
clear `terminal-native-capture-authority-unavailable`.

There is a separate, explicitly **trusted reviewed-code** path below. It does not
confine arbitrary JavaScript. Missing explicit program approval remains fail-closed.

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

The caller may retain **only the actual `replayCapture` object** as diagnostic
`capture.json`; ordinary diagnostic v1 cannot pass `produce`. Use the separately
reviewed native-capture path below for mechanically admissible native evidence.
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

## Real-source regression fixture

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

## Host-approved exact source closure

`reviewed-capture` and `reviewed-replay` accept the same explicit runtime argv as
`capture`/`replay`. They preserve the actual delivered factory and every requested
state, and additionally return the helper's live native IDs/types/parents/bounds
and visibility-isolation frames. Every PNG is captured externally via CDP, including
isolation and reset; the driver cross-checks the returned native capture against
the actual external frame map. The producer is the distinct
`pixi2d-external-native-capture-v1`, never a relabelled diagnostic v1. The envelope
still does not grant approval or terminal acceptance. Save its `replayCapture` as
the candidate capture, then produce/review/publish normally; the plugin only checks
mechanical completeness. Do not rewrite an already-reviewed artifact to match.

The base's `pixi_capture_authority.py` exposes:

```python
authority = PixiCaptureAuthority(live_program_approved_policies)
receipt = authority.verify_capture(
    child_workspace, object_id=object_id, revision=revision,
    artifact_binding={"path": artifact_path, "sha256": artifact_raw_sha},
    snapshot_binding={"path": snapshot_path, "sha256": snapshot_raw_sha},
    reference_binding={"path": reference_path, "sha256": admitted_reference_sha},
    requirements=program_approved_requirements,
)
```

Only host/program code may construct a frozen `ReviewedPixiPolicy` after actually
inspecting the exact source closure and approved dependencies. Required fields:
`object_id`, `revision`, `snapshot_binding`, `reference_binding`,
`requirements_json`, `sources`, `assets`, `plugin_root`, `node`,
`runtime_options`, `runtime_lock_json`, `review_id`, `review_notes`.
Bindings are `(relative_path, sha256)` tuples; source/asset lists are tuples of
bindings; JSON fields are canonical UTF-8 bytes; runtime options are a tuple of
the four `(option, absolute_canonical_path)` pairs above. Runtime locks pin the
whole Pixi/Playwright/core/browser trees, Node executable and host/helper/driver.
Review identifiers/notes describe the actual review, not candidate-authored flags.
There is no JSON policy loader or automatic source approval. The live map is
retained and checked before/after replay so removing or changing approval revokes it.

The bridge independently re-reads approved source/resources, snapshot/reference,
current artifact/capture/evidence/review and every runtime pin. It runs the pinned
program-owned driver in a disposable fresh browser against the exact factory,
compares the complete current native capture (baseline, isolation, edits, behavior
and resets), independently checks native IDs/bounds against pixel footprints and
unambiguous independent ownership, then rechecks input/runtime pins and live
approval. It returns observed evidence or raises `ParentError`; it never writes
child files. No approval means `terminal-native-capture-authority-unavailable`.
The parent still owns terminal gate, authenticated semantic review and promotion.

**Trust statement:** reviewed exact sources and approved dependencies are trusted
code. This does **not** establish confinement/security for arbitrary same-realm
JavaScript or source-to-build equivalence. Hashes alone are not code review.
Synthetic fixture replay proves technical native capture behavior, not artwork
quality or reconstruction fidelity. Arbitrary submitted code remains unauthorized.

For the base bridge's disposable technical reproduction, explicitly select
`IMG2_PIXI_PLUGIN`, the same `IMG2_TEST_HARNESS`/`PIXI_REPLAY_RUNTIME` prerequisites,
and a working native-architecture Node on `PATH`, then run:

```sh
python3 /path/to/base/forge/tests/test_pixi_capture_authority.py --reproduce
```

After all writers finish, the parent verifier can run the full new bridge probes:

```sh
python3 -m unittest discover -s /path/to/base/forge/tests -p test_pixi_capture_authority.py -v
```

The reproduction constructs only the inspected two-file regression factory,
produces actual external native evidence and an honestly unreviewed technical
candidate, then exercises capture authority. It does not invent semantic review,
publish a passed artifact or make the final terminal decision. No prerequisites
means an explicit refusal (or a named suite skip), never mock-browser success.
