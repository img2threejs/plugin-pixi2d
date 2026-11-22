# Harness: explicit 2D, editable evidence, blocking review

The root manifest contributes **`image → pixi2d-scene`** and the D3 card declares
`outputKind: 2d-scene`. The base alone enforces explicit-2D eligibility. A 3D
request must never enter this branch. Explicit 2D skips decomposition/composition;
this artifact deliberately does not claim D18 metric scale, a 3D frame or a rig.
The OMP workflow and existing `forge.cli` image tools remain available unchanged.

`$SKILL_DIR` below is the repository root, not `skills/img2pixi2d`.
Harness tools require Python ≥3.10 and linked `img2_core` API 1. They are stdlib-only,
offline, never install dependencies and never contact Jev or another service.
Image admission/crop/compare still use the existing declared Pillow environment.
The host must already provide PixiJS v8 and a real browser canvas. No second app,
renderer, demo or scene generator is supplied.

## 1. Freeze the actual requirements

Before rendering, author `.img2/artifacts/pixi2d/inputs.json` in the user's project.
This is a **schema example**, not evidence to copy as a completed reconstruction:

```json
{
  "kind": "img2.pixi2d-inputs",
  "version": 1,
  "objectId": "whole-image",
  "reference": ".img2pixi2d/reference/working.png",
  "spec": ".img2pixi2d/reconstruction.json",
  "profile": ".img2pixi2d/profile.json",
  "sources": ["src/subject.ts"],
  "assets": ["art/owner.png", "art/owner.meta.json", "art/LICENSE.txt"],
  "requiredNodes": [
    {"id": "owner", "type": "Sprite", "edits": ["position", "visibility"]},
    {"id": "caption", "type": "Text", "edits": ["text", "visibility"]}
  ],
  "criticalFeatures": [{"id": "identity-mark", "bbox": [12, 16, 40, 32]}],
  "behaviorChecks": [
    {"id": "lifecycle", "description": "Dispose/recreate and verify another consumer retains shared resources", "changesPixels": false},
    {"id": "motion-end", "description": "Requested end pose; other effects frozen; protected neighbours intact", "changesPixels": true}
  ],
  "scopedCandidates": {"build-strategy": [], "repair": []}
}
```

- All paths are canonical, workspace-relative, contained file paths. Sources must
  include the delivered editable JS/TS factory, **not just a raster or report**.
  Include every source module and loaded resource influencing this reconstruction;
  include permitted font bytes, layer provenance and licences in `assets`.
- The original reconstruction plan remains subject-specific. Do not replace it
  with a generic descriptor or strip its ownership, permission or motion data.
  The render profile is a JSON object with integer `width`/`height` equal to the
  admitted reference pixels, plus the actual resolution, background, clipping,
  renderer, state/time and font/asset readiness settings used by the existing host.
- `requiredNodes` has unique ids, native `Container|Graphics|Text|Sprite|Mesh`
  types and one or more `position|visibility|text` edits. Every independent text,
  moving or interactive part must appear. `text` requires native `Text`.
  A Container-only scene is refused. A lone renderable Sprite is refused unless
  `atomicGraphic: true` reflects an actually atomic graphic with no internal edit
  requirement. Multiple placeholder nodes do not legitimize a raster-only scene;
  the mandatory requirements/ownership review must reject that mismatch.
- Bboxes are integer `[x,y,width,height]` inside the reference; use actual observed
  critical regions. Required features cannot be silently omitted or downgraded.
- `behaviorChecks` must include `lifecycle`. Add every requested interaction,
  start/end/extremum/crossing, combined state and failing state as separate named
  checks. A neutral image and one extremum are not a full motion review. Record
  continuous coverage, refined samples and limitations in the spec/review reasons.
  `changesPixels: false` is for genuinely nonvisual behavior (for example
  dispose/recreate), not a way to waive visible requested edits.
- Candidate arrays are bounded **data for the base controller**, not commands.
  Each entry has exactly `id`, `operations`, `componentIds`, `specFields`,
  `prerequisites`, `expectedMeasurements`; the latter three are string arrays.
  Operations are `hierarchy|graphics|text|sprite|mesh|material|motion|input-evidence`;
  component ids must be declared nodes. The base still checks pass locks,
  provenance, dependencies, budgets, permissions and admissibility before use.
  Empty arrays mean no proposed actions, not an automatically selected plan.

Bind the current inputs, reference, spec, profile, source and asset bytes:

```sh
python3 "$SKILL_DIR/tools/pixi2d.py" snapshot --workspace "$PWD"
```

The program writes `snapshot.json` under `.img2/artifacts/pixi2d/`. Spec and profile
bindings use raw bytes (stricter than the standalone historical canonical-spec
convention). Keep mutable history separate. A changed input requires a new
snapshot and new downstream capture/review; preserve previous revisions in the
base-owned child/candidate workspace. This tool never resets shared counters or
creates its own decision lifecycle.

## 2. Produce real runtime captures

Use `runtime/review-capture.mjs` in the **actual existing project**, imported through
its existing module tooling. Pass the existing Application, the actual PixiJS
namespace imported by that host, the returned scene handle `{root, nodes}` (Map
or object), the parsed snapshot, and real `behaviors` callbacks:

```js
const capture = await captureEditableScene({ app, handle, PIXI, snapshot, behaviors });
```

Each behavior id maps to `{run: asyncFunction, reset: asyncFunction}` implemented
against the real host. Supply the actual dispose/recreate/shared-consumer check;
there is intentionally no generic fake lifecycle callback. Use the host's existing
browser automation/download channel to save the returned JSON as `capture.json`
in the artifact directory. Keep the actual source revision loaded and verify it
matches the bound source modules; an old hot-reload session is stale evidence.

The producer checks the root is attached to the host, verifies native node types,
rejects aliasing one node under multiple ids, mutates each declared node, captures
its canvas and restores it in `finally`. It executes every requested behavior and
reset. The host must settle fonts/assets, freeze unrelated animation and retain a
readable WebGL drawing buffer for immediate `canvas.toDataURL` after render (see
`pixijs.md`). Readback failures block; do not replace them with screenshots of code,
original reference pixels or a separately rendered imitation.

Capture v2 records each declared node's native bounds, parent, visibility, and
isolated/restored frames from a visibility toggle in the live host. The verifier
derives changed-pixel regions from those frames, checks bounds and reset, and
rejects ambiguous independent ownership. A node without visible pixels requires
an explicit `noPixelFootprint` justification in the frozen requirements. Legacy
v1 and CDP replay captures cannot satisfy this contract. These checks do not
authenticate the host or establish visual quality; independent review remains required.

```sh
python3 "$SKILL_DIR/tools/pixi2d.py" produce --workspace "$PWD"
```

This deterministic producer rechecks current bindings; decodes real RGB/RGBA8,
noninterlaced PNGs with bounded decompression and CRC checks; checks matching
artboard sizes, every required edit/behavior capture and reset; rejects edits
without a visible pixel change; and requires reset pixels to equal baseline.
It writes content-hashed PNGs and **native-resolution reference/render critical
crops generated from the actual bound images**, plus `evidence.json`.

This is evidence admission, not a visual judgment. Pixel changes alone cannot
prove that text is unbaked, occluded art is complete, neighbours are protected,
fonts are correct or a motion cycle is acceptable. Existing `forge.cli compare`
remains useful diagnostics, never a substitute for the following review.

## 3. Native review must be complete and current

Inspect the actual saved reference and baseline, every edit/behavior/reset, both
crops for every critical feature, source/spec/profile and resource provenance.
Author `review.json` with these fields:

- `kind: img2.pixi2d-review`, `version: 1`.
- `snapshotSha256`: `evidence.json`'s `snapshotSha256`.
- `evidenceSha256`: SHA256 of canonical JSON for the parsed `evidence.json`.
- `reviewer: {id: actualReviewerIdentity, method: "native-vision"}`.
- `unresolvedDefects`: an empty array **only when there are no unresolved defects**.
- `inspected`: the exact concatenation of `snapshot.bindings` and `evidence.files`
  entries (`{path,sha256}`), only after actually inspecting them.
- `assessments`: exactly one row for each id in `snapshot.checks`, with
  `{id, judgment, score, reason, evidence}`. `evidence` is a nonempty list of actual
  produced PNG paths. Every feature must cite both of its generated crops; every
  edit/behavior must cite its own changed-state capture. Inspect/reset evidence
  is mandatory even when the source factory appears correct.

Required global ids are `requirements`, `layout`, `identity`, `ownership`,
`motion-coverage`, `provenance`, `lifecycle`, followed by every declared edit,
critical feature and behavior. `requirements` checks completeness against the
actual user request, not only this JSON. `ownership` checks unbaked independent
parts and protected neighbours. `motion-coverage` checks the full requested
motion/interaction envelope; for a static request explicitly explain that fact.
`lifecycle` checks actual disposal/recreation, not just existence of a method.

Use the frozen 0–4 rubric: 0 absent/wrong, 1 major mismatch, 2 partial, 3 meets the
declared requirement, 4 exceeds it. Record observed reasons, never default scores.
Only `judgment: pass` with score ≥3 is admissible for **every** required row.
Missing/unevaluated/uncertain/fail, low scores, missing evidence, unresolved defects
and stale bindings all block. A strong average cannot compensate for one failed
critical feature. Unavailable fonts, requested hidden artwork or continuous
coverage require input, not fabricated acceptance or reduced motion.

Canonical JSON uses sorted keys, UTF-8, compact separators, no nonfinite numbers.
For example, hash a parsed JSON object with
`hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()`.
The capture helper computes the snapshot digest itself; no hash is a vision score.

## 4. Publish and integrate

```sh
python3 "$SKILL_DIR/tools/pixi2d.py" publish --workspace "$PWD"
python3 "$SKILL_DIR/tools/pixi2d.py" gate --workspace "$PWD"
```

`publish` validates everything again before atomically writing `artifact.json`.
It is `img2.pixi2d-scene` v1 with `objectId`, `outputKind: 2d-scene`,
`coordinates: {units: reference-pixels, origin: top-left, x: right, y: down}`,
`artboard: [width,height]`, `editableSources`, `assets`, `bindings`, `evidence`,
`review`, `snapshotSha256`, `evidenceSha256`. Every file entry is
`{path: workspaceRelativePath, sha256: actualByteHash}`. It references the delivered
source and resources in-place; it never flattens or replaces the editable output.

The blocking gate `pixi2d-editable-review` rechecks current snapshots, captures,
produced images, review and exact published artifact. It emits one
`img2.gate-verdict` v1 (0 pass / 1 fail); non-gate adapter commands return 2 when
blocked. Missing review/capture/artifact is a failure, not an opt-out. The harness
runner enforces the blocking result:

```sh
python3 -m img2_core.gate_runner --plugin-dir "$SKILL_DIR" --workspace "$PWD"
```

For D21 integration, read `snapshot.json` (bound inputs, requirements and scoped
strategy/repair candidates), `evidence.json` (fresh render/crop files and capture
binding), and the gate envelope. Base-owned routing/strategy/review/repair remain
one shared controller with one budget. No cross-repository implementation imports
or plugin-authored canonical workflow action are introduced. A semantic advisory
may block; it cannot clear this gate. The base explicitly branches on `2d-scene`
instead of passing this artwork to the 3D artifact validator/composer.

## Trust and verification limits

These hashes and runtime reports establish consistency and enforce completeness;
they do not authenticate an external reviewer's identity, attest a browser process
or mathematically prove visual correctness. Native host inspection and honest
capture provenance remain required. Do not represent the offline fixture tests as
real PixiJS rendering, real vision, requested-image fidelity or integrated quality.
No runtime reconstruction was performed merely by adding this adapter.

Focused verifier commands from the repository root (after all writers finish):

```sh
IMG2_TEST_HARNESS=/absolute/path/to/img2 python3 -m unittest discover -s tests -v
node --test tests/review-capture.test.mjs
```

The Python tests isolate `IMG2_HOME`, use the actual read-only harness runner and
exercise both passing protocol fixtures and blocking negatives. The JS tests use
explicit unit doubles and do not claim browser evidence. A separately authorized
real-host run must still supply the user's image, actual editable factory, native
captures and reviewer observations before the runtime/visual acceptance gate can
be claimed passed. Registration/doctor/sync need their own disposable harness
registry or explicit authorization; nothing here mutates installed plugins.

## Program-owned diagnostic replay

`replay.md` documents the explicit frozen `createRoutedPixiScene` ESM ABI,
complete executable/resource bindings and optional isolated Chromium replay.
The program captures real CDP viewport PNGs rather than trusting page-controlled
`canvas.toDataURL`; it writes no reviewed records. The replay driver captures
v2 isolation frames for protocol sequencing but omits them from the diagnostic
replay artifact. `pixi2d-cdp-replay-v1` remains nonauthoritative and the evidence
producer refuses it; use an actual native capture for the independent review path.

Diagnostic replay and the plugin gate alone never grant terminal authority.
Arbitrary entry/behavior JavaScript shares mutable renderer/browser objects;
matching pixels and native-looking objects cannot establish unforgeable
native-node-to-pixel provenance or confinement.

The separate `reviewed-capture`/`reviewed-replay` path emits
`pixi2d-external-native-capture-v1` with externally captured isolation frames and
live native bounds/IDs. It is mechanically admissible to this evidence producer,
but its producer string is not approval. The base's `PixiCaptureAuthority` requires
a live, frozen host-created `ReviewedPixiPolicy` covering the exact reviewed ESM
source/resource closure, snapshot, reference, requirements and all dependencies.
It independently re-reads those bytes, replays the actual delivered factory in
the pinned owned browser, compares all current captures and validates native
IDs/bounds/pixel footprints before returning observed evidence. See `replay.md`
for the exact API. No explicit source review means
`terminal-native-capture-authority-unavailable`; candidate/model/workspace JSON
cannot grant source approval.

Reviewed source closure and approved dependencies are trusted code. This does
**not** establish confinement/security for arbitrary same-realm JavaScript,
source-to-build equivalence or artwork quality. Parent-owned blocking gates and
authenticated semantic quality review remain independently necessary.
