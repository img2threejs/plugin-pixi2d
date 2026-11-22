---
name: img2-pixi2d
description: Reconstruct explicitly requested editable PixiJS 2D artwork in an existing project, with independent nodes, provenance, real canvas evidence and blocking native visual review. Never use for 3D requests.
---

`$SKILL_DIR` is the directory containing this file. Follow
`skills/img2pixi2d/SKILL.md` for the existing intake, authoring, ownership,
occlusion and motion workflow. Preserve the host Application, ticker and resources.

For harness routing, read `skills/img2pixi2d/references/harness-review.md`.
The edge is `image → pixi2d-scene`; the route output kind is `2d-scene`.
Only the base decides explicit-2D eligibility; skip 3D composition. This plugin
provides no 3D artifact, inferred metric scale, shared decision controller,
provider call, auth handling or quality override.

After authoring the frozen inputs contract in the user's project:

```sh
python3 "$SKILL_DIR/tools/pixi2d.py" snapshot --workspace "$PWD"
```

Use the actual host and `skills/img2pixi2d/runtime/review-capture.mjs` to capture
editable-node probes and requested behavior, not a substitute renderer/demo.
Then produce the bound capture files and inspect them using native host vision:

```sh
python3 "$SKILL_DIR/tools/pixi2d.py" produce --workspace "$PWD"
python3 "$SKILL_DIR/tools/pixi2d.py" publish --workspace "$PWD"
```

Publication requires a complete fresh `review.json` as documented in the contract.
The blocking gate reruns those same validations and also checks the published
artifact. Hashes prove bindings, not visual correctness. Missing images,
unexecuted edits, incomplete full-envelope review, critical defects and uncertain
judgments block completion. A Jev advisory cannot clear this gate; the base alone
publishes canonical workflow actions. No paid/network calls are made here.

For program-owned **diagnostic** ESM/CDP replay, read
`skills/img2pixi2d/references/replay.md`. It requires the exact delivered factory's
explicit routed ESM ABI and independently held runtime pins; unsupported original
hosts block rather than receiving substitute geometry. It never trusts
page-controlled `toDataURL`. Same-realm native-node provenance remains
`unevaluated` and `terminalAcceptance` remains false; neither this replay nor
the plugin review gate clears the base's native-capture-authority blocker.
