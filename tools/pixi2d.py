"""Offline harness adapter; evidence integrity never substitutes for native vision."""
import os
import sys

root = os.environ.get("IMG2_HOME")
if root:
    sys.path.insert(0, os.path.join(root, "harness"))
else:
    try:
        import _img2_local
        sys.path.insert(0, _img2_local.CORE)
    except ImportError:
        sys.exit("img2: core not linked - run `img2 sync`")
from img2_core import require_core_api
require_core_api(1)

import argparse
import base64
import hashlib
import json
import math
import re
import struct
import tempfile
import zlib
from pathlib import Path

AREA = Path(".img2/artifacts/pixi2d")
GATE = "pixi2d-editable-review"
TYPES = {"Container", "Graphics", "Text", "Sprite", "Mesh"}
CHECKS = ["requirements", "layout", "identity", "ownership", "motion-coverage", "provenance", "lifecycle"]
OPERATIONS = {"hierarchy", "graphics", "text", "sprite", "mesh", "material", "motion", "input-evidence"}
NATIVE_PRODUCER = "pixi2d-native-capture-v2"
EXTERNAL_NATIVE_PRODUCER = "pixi2d-external-native-capture-v1"
LEGACY_NATIVE_PRODUCER = "pixi2d-native-capture-v1"
REPLAY_PRODUCER = "pixi2d-cdp-replay-v1"
PROVENANCE_CONTRACT = "img2.pixi2d-node-provenance/v1"
ISOLATION_METHOD = "visibility-toggle"
BOUNDS_TOLERANCE_PX = 2  # raster/antialiasing spread tolerated outside a node's reported bounds


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def reject_constant(value):
    raise ValueError("non-finite-json")


def read_json(path):
    require(path.stat().st_size <= 32 * 1024 * 1024, "json-too-large")
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)


def local(workspace, name):
    require(isinstance(name, str) and name and not Path(name).is_absolute(), "workspace-relative-path-required")
    path = (workspace / name).resolve()
    require(path.is_relative_to(workspace), "path-escapes-workspace")
    require(path.relative_to(workspace).as_posix() == name, "noncanonical-path")
    return path


def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def save(workspace, name, value):
    atomic(local(workspace, str(AREA / name)), encoded(value) + b"\n")


def binding(workspace, name):
    path = local(workspace, name)
    require(path.is_file(), "missing-file:" + name)
    return {"path": name, "sha256": digest(path.read_bytes())}


def identifier(value):
    require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", value), "invalid-id")
    return value


def png(data):
    """Decode bounded, CRC-checked RGB/RGBA8 PNGs; reject text and truncated images."""
    require(len(data) <= 20 * 1024 * 1024 and data[:8] == b"\x89PNG\r\n\x1a\n", "invalid-png")
    offset, chunks, header, ended = 8, [], None, False
    while offset < len(data):
        require(offset + 12 <= len(data), "truncated-png")
        length = struct.unpack_from(">I", data, offset)[0]
        tag = data[offset + 4:offset + 8]
        body = data[offset + 8:offset + 8 + length]
        require(offset + length + 12 <= len(data), "truncated-png")
        crc = struct.unpack_from(">I", data, offset + 8 + length)[0]
        require(zlib.crc32(tag + body) & 0xffffffff == crc, "png-crc-mismatch")
        require(header is not None or tag == b"IHDR", "png-header-required")
        if tag == b"IHDR":
            require(header is None and length == 13, "invalid-png-header")
            header = struct.unpack(">IIBBBBB", body)
        elif tag == b"IDAT":
            chunks.append(body)
        elif tag == b"IEND":
            require(length == 0 and offset + 12 == len(data), "invalid-png-end")
            ended = True
        elif tag[:1].isupper():
            require(tag == b"PLTE", "unsupported-png-chunk")
        offset += length + 12
    require(header is not None and ended and chunks, "incomplete-png")
    width, height, depth, color, compression, filtering, interlace = header
    require(0 < width <= 8192 and 0 < height <= 8192 and width * height <= 32_000_000, "png-size-limit")
    require(depth == 8 and color in (2, 6) and compression == filtering == interlace == 0, "require-rgb-or-rgba8-noninterlaced-png")
    channels = 4 if color == 6 else 3
    stride = width * channels
    expected = (stride + 1) * height
    decoder = zlib.decompressobj()
    raw = decoder.decompress(b"".join(chunks), expected + 1)
    require(len(raw) == expected and decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail, "invalid-png-pixels")
    pixels, previous = bytearray(width * height * 4), bytearray(stride)
    for y in range(height):
        start = y * (stride + 1)
        mode = raw[start]
        require(mode <= 4, "invalid-png-filter")
        row = bytearray(raw[start + 1:start + 1 + stride])
        for x in range(stride):
            left = row[x - channels] if x >= channels else 0
            above = previous[x]
            corner = previous[x - channels] if x >= channels else 0
            if mode == 1:
                row[x] = (row[x] + left) & 255
            elif mode == 2:
                row[x] = (row[x] + above) & 255
            elif mode == 3:
                row[x] = (row[x] + (left + above) // 2) & 255
            elif mode == 4:
                estimate = left + above - corner
                distances = [abs(estimate - candidate) for candidate in (left, above, corner)]
                prediction = (left, above, corner)[distances.index(min(distances))]
                row[x] = (row[x] + prediction) & 255
        target = y * width * 4
        if channels == 4:
            pixels[target:target + width * 4] = row
        else:
            for x in range(width):
                pixels[target + x * 4:target + x * 4 + 4] = row[x * 3:x * 3 + 3] + b"\xff"
        previous = row
    return width, height, pixels


def crop_png(image, box):
    width, _, pixels = image
    x, y, w, h = box
    raw = b"".join(b"\0" + pixels[((y + row) * width + x) * 4:((y + row) * width + x + w) * 4] for row in range(h))
    def chunk(tag, body):
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def capture_frame(url, snapshot, reason):
    """Admit one captured PNG: a real data URL that decodes at exactly the artboard size."""
    require(isinstance(url, str) and url.startswith("data:image/png;base64,"), reason)
    data = base64.b64decode(url.split(",", 1)[1], validate=True)
    image = png(data)
    require(list(image[:2]) == snapshot["artboard"], "capture-frame-mismatch")
    return image, data


def changed_pixels(base, other):
    """One 0/1 byte per pixel: 1 where any RGBA channel differs between two equal-size buffers."""
    return bytes(a != b for a, b in zip(memoryview(base).cast("I"), memoryview(other).cast("I")))


def region_of(flags, width):
    """Tight [x, y, width, height] box around the set pixels, or None when no pixel changed."""
    first = flags.find(1)
    if first < 0:
        return None
    top, bottom = first // width, flags.rfind(1) // width
    left, right = width, -1
    for y in range(top, bottom + 1):
        row = flags[y * width:(y + 1) * width]
        start = row.find(1)
        if start >= 0:
            left, right = min(left, start), max(right, row.rfind(1))
    return [left, top, right - left + 1, bottom - top + 1]


def disjoint(a, b):
    return a[0] + a[2] <= b[0] or b[0] + b[2] <= a[0] or a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1]


def node_provenance(capture, snapshot, baseline, visibility_frames, profile_resolution):
    """Verify the capture's per-node provenance and return the measured evidence.

    Every pixel region, footprint, overlap and exclusive-pixel count below is derived
    here from the captured isolation frames. Nothing is read from a producer-reported
    region or inferred from source text. A node without a measurable footprint must
    carry a justification in the frozen requirements and is still measured to be empty.
    Bounds, parent links and resolution are scene-graph values the capture runtime
    measured in the live host; they are cross-checked against the pixels, never
    used to produce them. Pixel evidence cannot authenticate the host that produced it.
    """
    provenance = capture.get("provenance")
    require(isinstance(provenance, dict), "node-provenance-missing")
    require(set(provenance) == {"contract", "resolution", "nodes"} and provenance["contract"] == PROVENANCE_CONTRACT, "invalid-node-provenance-contract")
    resolution = provenance["resolution"]
    require(finite(resolution) and resolution > 0, "invalid-node-provenance-resolution")
    require(profile_resolution is None or resolution == profile_resolution, "node-provenance-resolution-mismatch")
    records = provenance["nodes"]
    require(isinstance(records, list), "invalid-node-provenance-records")
    nodes = snapshot["requirements"]["requiredNodes"]
    declared = {node["id"] for node in nodes}
    by_id = {}
    for record in records:
        ident = record.get("id") if isinstance(record, dict) else None
        require(isinstance(ident, str), "invalid-node-provenance-record")
        require(ident in declared, "node-provenance-unexpected:" + ident)
        require(ident not in by_id, "node-provenance-duplicate:" + ident)
        by_id[ident] = record
    width, height = snapshot["artboard"]
    order, parents, measured, result = [], {}, {}, {}
    for node in nodes:
        ident = node["id"]
        record = by_id.get(ident)
        require(record is not None, "node-provenance-missing:" + ident)
        require(set(record) == {"id", "type", "parent", "visibleAtBaseline", "bounds", "isolation"}, "invalid-node-provenance-record:" + ident)
        require(record["type"] == node["type"], "node-provenance-identity-mismatch:" + ident)
        parent = record["parent"]
        require(parent is None or (isinstance(parent, str) and parent in declared and parent != ident), "node-provenance-invalid-parent:" + ident)
        parents[ident] = parent
        require(type(record["visibleAtBaseline"]) is bool, "invalid-node-provenance-record:" + ident)
        bounds = record["bounds"]
        require(isinstance(bounds, dict) and set(bounds) == {"x", "y", "width", "height"} and all(finite(value) for value in bounds.values()) and bounds["width"] >= 0 and bounds["height"] >= 0, "node-bounds-invalid:" + ident)
        isolation = record["isolation"]
        require(isinstance(isolation, dict) and set(isolation) == {"method", "isolated", "restored", "restoredVisible"} and isolation["method"] == ISOLATION_METHOD and type(isolation["restoredVisible"]) is bool, "invalid-node-isolation-record:" + ident)
        require(isolation["restoredVisible"] is record["visibleAtBaseline"], "node-restore-mismatch:" + ident)
        isolated, isolated_data = capture_frame(isolation["isolated"], snapshot, "real-png-isolation-capture-required:" + ident)
        restored, restored_data = capture_frame(isolation["restored"], snapshot, "real-png-isolation-capture-required:" + ident)
        require(restored[2] == baseline, "node-restore-mismatch:" + ident)
        flags = changed_pixels(baseline, isolated[2])
        pixels = flags.count(1)
        region = region_of(flags, width)
        justification = node.get("noPixelFootprint")
        if justification is not None:
            require(pixels == 0, "declared-empty-footprint-contradicted:" + ident)
        else:
            require(pixels > 0, "node-footprint-empty:" + ident)
            require(bounds["width"] > 0 and bounds["height"] > 0, "node-bounds-empty:" + ident)
            left, top = bounds["x"] * resolution, bounds["y"] * resolution
            right, bottom = left + bounds["width"] * resolution, top + bounds["height"] * resolution
            require(right > 0 and bottom > 0 and left < width and top < height, "node-bounds-outside-artboard:" + ident)
            x, y, w, h = region
            require(x >= math.floor(left) - BOUNDS_TOLERANCE_PX and y >= math.floor(top) - BOUNDS_TOLERANCE_PX and x + w <= math.ceil(right) + BOUNDS_TOLERANCE_PX and y + h <= math.ceil(bottom) + BOUNDS_TOLERANCE_PX, "node-region-outside-bounds:" + ident)
            measured[ident] = {"region": region, "mask": int.from_bytes(flags, "little")}
        if "visibility" in node["edits"]:
            # The visibility edit toggles exactly the node the isolation toggled, from the same baseline state.
            require(visibility_frames[ident] == isolated[2], "isolation-differs-from-visibility-edit:" + ident)
        order.append(ident)
        result[ident] = {"id": ident, "type": node["type"], "parent": parent, "footprint": "measured" if justification is None else "declared-none", "justification": justification, "bounds": bounds, "region": region, "pixels": pixels, "exclusivePixels": 0, "isolatedSha256": digest(isolated_data), "restoredSha256": digest(restored_data)}
    ancestors = {}
    for ident in order:
        chain, current = set(), parents[ident]
        while current is not None:
            require(current != ident and current not in chain, "node-provenance-parent-cycle:" + ident)
            chain.add(current)
            current = parents[current]
        ancestors[ident] = chain
    overlaps, rivals = [], {ident: [] for ident in measured}
    ids = [ident for ident in order if ident in measured]
    for index, first in enumerate(ids):
        for second in ids[index + 1:]:
            a, b = measured[first], measured[second]
            if disjoint(a["region"], b["region"]):
                continue
            shared = (a["mask"] & b["mask"]).bit_count()
            if not shared:
                continue
            nested = first in ancestors[second] or second in ancestors[first]
            overlaps.append({"a": first, "b": second, "relation": "nested" if nested else "independent", "sharedPixels": shared})
            if not nested:
                rivals[first].append(second)
                rivals[second].append(first)
    # Co-changed pixels are reported, never assigned to one node. A node whose every
    # measured pixel is also changed by an unrelated node has no independently
    # established region, so ownership is ambiguous and the capture is refused.
    ambiguous = []
    for ident in ids:
        taken = 0
        for rival in rivals[ident]:
            taken |= measured[rival]["mask"]
        result[ident]["exclusivePixels"] = (measured[ident]["mask"] & ~taken).bit_count()
        if not result[ident]["exclusivePixels"]:
            ambiguous.append("ambiguous-node-ownership:%s:no-exclusive-pixels:shared-with=%s" % (ident, ",".join(rivals[ident])))
    require(not ambiguous, ";".join(ambiguous))
    return {"status": "measured", "contract": PROVENANCE_CONTRACT, "resolution": provenance["resolution"], "boundsTolerancePx": BOUNDS_TOLERANCE_PX, "nodes": [result[ident] for ident in order], "overlaps": overlaps}


def current_snapshot(workspace):
    inputs_path = str(AREA / "inputs.json")
    inputs = read_json(local(workspace, inputs_path))
    require(inputs.get("kind") == "img2.pixi2d-inputs" and inputs.get("version") == 1, "invalid-inputs-contract")
    identifier(inputs["objectId"])
    profile = read_json(local(workspace, inputs["profile"]))
    require(type(profile["width"]) is int and type(profile["height"]) is int, "integer-artboard-required")
    reference = png(local(workspace, inputs["reference"]).read_bytes())
    require([profile["width"], profile["height"]] == list(reference[:2]), "reference-profile-size-mismatch")
    require(isinstance(read_json(local(workspace, inputs["spec"])), dict), "invalid-reconstruction-plan")
    nodes = inputs["requiredNodes"]
    require(isinstance(nodes, list) and nodes, "editable-nodes-required")
    ids = set()
    for node in nodes:
        identifier(node["id"])
        require(node["id"] not in ids and node["type"] in TYPES, "duplicate-or-invalid-node")
        ids.add(node["id"])
        edits = node["edits"]
        require(isinstance(edits, list) and edits and len(set(edits)) == len(edits), "node-edit-probes-required")
        require(set(edits) <= {"position", "visibility", "text"}, "unsupported-edit")
        require("text" not in edits or node["type"] == "Text", "native-text-required")
        require("noPixelFootprint" not in node or (isinstance(node["noPixelFootprint"], str) and bool(node["noPixelFootprint"].strip())), "invalid-no-pixel-footprint-justification")
    leaves = [node for node in nodes if node["type"] != "Container" and "noPixelFootprint" not in node]
    require(leaves, "renderable-editable-node-required")
    require(not (len(leaves) == 1 and leaves[0]["type"] == "Sprite") or inputs.get("atomicGraphic") is True, "raster-only-scene-refused")
    checks = list(CHECKS)
    for node in nodes:
        checks.extend("edit:" + node["id"] + ":" + edit for edit in node["edits"])
    feature_ids = set()
    for feature in inputs["criticalFeatures"]:
        identifier(feature["id"])
        require(feature["id"] not in feature_ids, "duplicate-critical-feature")
        feature_ids.add(feature["id"])
        box = feature["bbox"]
        require(isinstance(box, list) and len(box) == 4 and all(type(v) is int for v in box), "invalid-critical-bbox")
        x, y, w, h = box
        require(x >= 0 and y >= 0 and w > 0 and h > 0 and x + w <= reference[0] and y + h <= reference[1], "critical-bbox-outside-reference")
        checks.append("feature:" + feature["id"])
    behavior_ids = set()
    for behavior in inputs["behaviorChecks"]:
        identifier(behavior["id"])
        require(behavior["id"] not in behavior_ids and type(behavior["changesPixels"]) is bool and bool(behavior["description"].strip()), "invalid-behavior-check")
        behavior_ids.add(behavior["id"])
        checks.append("behavior:" + behavior["id"])
    require("lifecycle" in behavior_ids, "dispose-recreate-behavior-required")
    paths = [inputs_path, inputs["reference"], inputs["spec"], inputs["profile"]]
    require(isinstance(inputs["sources"], list) and inputs["sources"], "editable-source-required")
    for source in inputs["sources"]:
        require(Path(source).suffix in {".ts", ".tsx", ".js", ".jsx", ".mjs"} and local(workspace, source).read_text().strip(), "editable-source-module-required")
    require(isinstance(inputs["assets"], list), "asset-manifest-required")
    paths += inputs["sources"] + inputs["assets"]
    require(len(set(paths)) == len(paths), "duplicate-input-path")
    candidates = inputs.get("scopedCandidates", {"build-strategy": [], "repair": []})
    require(set(candidates) == {"build-strategy", "repair"}, "invalid-candidate-groups")
    for group in candidates.values():
        require(isinstance(group, list), "invalid-candidates")
        seen = set()
        for candidate in group:
            require(set(candidate) == {"id", "operations", "componentIds", "specFields", "prerequisites", "expectedMeasurements"}, "invalid-scoped-candidate")
            identifier(candidate["id"])
            require(candidate["id"] not in seen, "duplicate-candidate")
            seen.add(candidate["id"])
            require(candidate["operations"] and set(candidate["operations"]) <= OPERATIONS and candidate["componentIds"] and set(candidate["componentIds"]) <= ids, "candidate-outside-scope")
            for key in ("specFields", "prerequisites", "expectedMeasurements"):
                require(isinstance(candidate[key], list) and all(isinstance(v, str) and v.strip() for v in candidate[key]), "invalid-candidate-fields")
    result = {"kind": "img2.pixi2d-snapshot", "version": 1, "objectId": inputs["objectId"], "bindings": [binding(workspace, path) for path in paths], "requirements": {key: inputs[key] for key in ("requiredNodes", "criticalFeatures", "behaviorChecks")}, "checks": checks, "scopedCandidates": candidates, "artboard": list(reference[:2])}
    if "replay" in inputs:
        replay = inputs["replay"]
        require(set(replay) == {"abi", "entry", "modules", "assets"} and replay["abi"] == "img2.routed-pixi-scene/v1", "invalid-replay-abi")
        modules = replay["modules"]
        require(isinstance(modules, list) and modules and len(set(modules)) == len(modules) and replay["entry"] in modules, "explicit-replay-module-closure-required")
        require(set(modules) <= set(inputs["sources"]), "replay-module-not-editable-source")
        require(all(Path(path).suffix in {".js", ".mjs"} for path in modules), "replay-requires-browser-esm-no-typescript-fallback")
        require(isinstance(replay["assets"], list), "invalid-replay-assets")
        aliases = set()
        for asset in replay["assets"]:
            require(set(asset) == {"path", "alias", "type"} and asset["path"] in inputs["assets"], "replay-asset-not-bound")
            identifier(asset["alias"])
            require(asset["alias"] not in aliases and asset["type"] in {"texture", "font", "json", "bytes"}, "invalid-replay-asset")
            aliases.add(asset["alias"])
        result["replay"] = replay
    return result


def fresh_snapshot(workspace):
    saved = read_json(local(workspace, str(AREA / "snapshot.json")))
    require(saved == current_snapshot(workspace), "stale-snapshot")
    return saved, digest(encoded(saved))


def capture_evidence(workspace, snapshot, snapshot_sha, write=False):
    capture = read_json(local(workspace, str(AREA / "capture.json")))
    require(capture.get("kind") == "img2.pixi2d-capture" and capture.get("version") == 1, "invalid-capture-contract")
    require(capture["snapshotSha256"] == snapshot_sha, "stale-capture")
    require(capture["renderer"] == "pixi.js" and re.fullmatch(r"8\.[0-9]+\.[0-9]+(?:[-+].*)?", capture["pixiVersion"]), "native-pixi8-capture-required")
    producer = capture.get("producer")
    require(producer != LEGACY_NATIVE_PRODUCER, "capture-predates-node-provenance-contract")
    if producer == REPLAY_PRODUCER:
        # External CDP pixels may corroborate a native capture; same-realm replay never establishes node provenance.
        raise ValueError("cdp-replay-cannot-satisfy-node-provenance")
    # This external producer is mechanically admissible, NOT source-review authority.
    # Only the base's independently approved live replay can authorize delivery.
    require(producer in {NATIVE_PRODUCER, EXTERNAL_NATIVE_PRODUCER}, "native-pixi8-capture-required")
    require(isinstance(capture.get("provenance"), dict), "node-provenance-missing")
    require(capture["nodes"] == snapshot["requirements"]["requiredNodes"], "runtime-nodes-mismatch")
    expected = {"baseline"}
    changing = set()
    for node in capture["nodes"]:
        for edit in node["edits"]:
            key = "edit-" + node["id"] + "-" + edit
            expected.update({key, key + "-reset"})
            if "noPixelFootprint" not in node:
                changing.add(key)
    for behavior in snapshot["requirements"]["behaviorChecks"]:
        key = "behavior-" + behavior["id"]
        expected.update({key, key + "-reset"})
        if behavior["changesPixels"]:
            changing.add(key)
    require(set(capture["images"]) == expected, "missing-or-unexpected-capture")
    files, baseline, visibility_frames = [], None, {}
    for key in ["baseline"] + sorted(expected - {"baseline"}):
        image, data = capture_frame(capture["images"][key], snapshot, "real-png-capture-required")
        if key == "baseline":
            baseline = image[2]
        elif key.endswith("-reset"):
            require(image[2] == baseline, "reset-pixels-mismatch:" + key)
        elif key in changing:
            require(image[2] != baseline, "edit-has-no-visible-effect:" + key)
        if key.startswith("edit-") and key.endswith("-visibility") and not key.endswith("-reset"):
            visibility_frames[key[5:-11]] = image[2]
        name = str(AREA / "evidence" / (key + "." + digest(data) + ".png"))
        if write:
            atomic(local(workspace, name), data)
        require(local(workspace, name).read_bytes() == data, "missing-or-changed-produced-capture")
        files.append({"path": name, "sha256": digest(data)})
    inputs = read_json(local(workspace, str(AREA / "inputs.json")))
    profile = read_json(local(workspace, inputs["profile"]))
    node_evidence = node_provenance(capture, snapshot, baseline, visibility_frames, profile.get("resolution"))
    reference = png(local(workspace, inputs["reference"]).read_bytes())
    rendered = (*snapshot["artboard"], baseline)
    for feature in snapshot["requirements"]["criticalFeatures"]:
        for role, image in (("reference", reference), ("render", rendered)):
            data = crop_png(image, feature["bbox"])
            name = str(AREA / "evidence" / ("feature-" + feature["id"] + "-" + role + "." + digest(data) + ".png"))
            if write:
                atomic(local(workspace, name), data)
            require(local(workspace, name).read_bytes() == data, "missing-or-changed-critical-crop")
            files.append({"path": name, "sha256": digest(data)})
    return {"kind": "img2.pixi2d-evidence", "version": 1, "snapshotSha256": snapshot_sha, "capture": binding(workspace, str(AREA / "capture.json")), "files": files, "nodeProvenance": node_evidence}


def accepted_artifact(workspace):
    snapshot, snapshot_sha = fresh_snapshot(workspace)
    evidence = capture_evidence(workspace, snapshot, snapshot_sha)
    require(read_json(local(workspace, str(AREA / "evidence.json"))) == evidence, "stale-produced-evidence")
    review = read_json(local(workspace, str(AREA / "review.json")))
    require(review.get("kind") == "img2.pixi2d-review" and review.get("version") == 1, "invalid-review-contract")
    require(review["snapshotSha256"] == snapshot_sha and review["evidenceSha256"] == digest(encoded(evidence)), "stale-review")
    require(review["reviewer"]["method"] == "native-vision" and bool(review["reviewer"]["id"].strip()), "native-visual-review-required")
    require(review["unresolvedDefects"] == [], "unresolved-review-defects")
    required_files = snapshot["bindings"] + evidence["files"]
    inspected = review["inspected"]
    require(isinstance(inspected, list) and len(inspected) == len(required_files) and sorted(inspected, key=lambda v: v["path"]) == sorted(required_files, key=lambda v: v["path"]), "incomplete-inspection")
    assessments = review["assessments"]
    require(isinstance(assessments, list) and len(assessments) == len(snapshot["checks"]) and {item["id"] for item in assessments} == set(snapshot["checks"]), "incomplete-review")
    evidence_paths = {item["path"] for item in evidence["files"]}
    for item in assessments:
        require(item["judgment"] == "pass" and type(item["score"]) in (int, float) and 3 <= item["score"] <= 4 and bool(item["reason"].strip()), "failed-or-uncertain-review:" + item["id"])
        require(isinstance(item["evidence"], list) and item["evidence"] and set(item["evidence"]) <= evidence_paths, "assessment-without-visual-evidence")
        if item["id"].startswith("feature:"):
            feature = item["id"].split(":", 1)[1]
            needed = {path for path in evidence_paths if Path(path).name.startswith("feature-" + feature + "-")}
            require(needed <= set(item["evidence"]), "critical-crops-not-reviewed")
        if item["id"].startswith("edit:"):
            _, node, edit = item["id"].split(":")
            require(any(Path(path).name.startswith("edit-" + node + "-" + edit + ".") for path in item["evidence"]), "edit-capture-not-reviewed")
        if item["id"].startswith("behavior:"):
            key = "behavior-" + item["id"].split(":", 1)[1]
            require(any(Path(path).name.startswith(key + ".") for path in item["evidence"]), "behavior-capture-not-reviewed")
    inputs = read_json(local(workspace, str(AREA / "inputs.json")))
    return {"kind": "img2.pixi2d-scene", "version": 1, "objectId": snapshot["objectId"], "outputKind": "2d-scene", "coordinates": {"units": "reference-pixels", "origin": "top-left", "x": "right", "y": "down"}, "artboard": snapshot["artboard"], "editableSources": [binding(workspace, path) for path in inputs["sources"]], "assets": [binding(workspace, path) for path in inputs["assets"]], "bindings": snapshot["bindings"], "evidence": evidence["files"], "review": binding(workspace, str(AREA / "review.json")), "snapshotSha256": snapshot_sha, "evidenceSha256": digest(encoded(evidence))}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("snapshot", "produce", "publish", "gate"))
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    result, code = {}, 0
    try:
        require(workspace.is_dir(), "workspace-required")
        # Resolve the output area before mkdir/write, including pre-existing symlinks.
        local(workspace, str(AREA))
        if args.command == "snapshot":
            result = current_snapshot(workspace)
            save(workspace, "snapshot.json", result)
        elif args.command == "produce":
            snapshot, sha = fresh_snapshot(workspace)
            result = capture_evidence(workspace, snapshot, sha, write=True)
            save(workspace, "evidence.json", result)
        else:
            artifact = accepted_artifact(workspace)
            if args.command == "publish":
                save(workspace, "artifact.json", artifact)
                result = artifact
            else:
                require(read_json(local(workspace, str(AREA / "artifact.json"))) == artifact, "missing-or-stale-published-artifact")
                result = {"kind": "img2.gate-verdict", "version": 1, "gate": GATE, "plugin": "pixi2d", "status": "pass", "reasons": [], "evidence": {"artifact": binding(workspace, str(AREA / "artifact.json"))}}
    except (OSError, ValueError, KeyError, TypeError, AttributeError, struct.error, zlib.error) as error:
        code = 1 if args.command == "gate" else 2
        result = {"kind": "img2.gate-verdict", "version": 1, "gate": GATE, "plugin": "pixi2d", "status": "fail", "reasons": [str(error) or type(error).__name__], "evidence": {}} if args.command == "gate" else {"status": "blocked", "reasons": [str(error) or type(error).__name__]}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
