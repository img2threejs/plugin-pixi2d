/** Run only inside the user's existing PixiJS host. No app, ticker or scene is created. */
const canonical = value => {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}`;
  }
  if (typeof value === 'number' && !Number.isFinite(value)) throw new Error('non-finite snapshot');
  return JSON.stringify(value);
};

const beneath = (node, root) => {
  for (let current = node; current; current = current.parent) if (current === root) return true;
  return false;
};

/**
 * Freeze host animations and wait for actual assets/fonts first. `behaviors` maps
 * every frozen behaviorChecks id to { run, reset } callbacks in the existing host.
 * A full motion envelope needs its own states/crossings/combined-state probes and
 * native continuous-coverage review; this helper never declares visual acceptance.
 * Save the returned JSON as .img2/artifacts/pixi2d/capture.json in the workspace.
 */
export async function captureEditableScene({ app, handle, PIXI, snapshot, behaviors = {}, captureFrame = null }) {
  if (snapshot.kind !== 'img2.pixi2d-snapshot' || snapshot.version !== 1) throw new Error('invalid snapshot');
  if (!(handle.root instanceof PIXI.Container) || !beneath(handle.root, app.stage)) throw new Error('scene is not in the actual host');
  if (!/^8\./.test(PIXI.VERSION)) throw new Error('PixiJS v8 required');
  if (app.canvas.width !== snapshot.artboard[0] || app.canvas.height !== snapshot.artboard[1]) throw new Error('actual canvas dimensions differ');
  const nodeFor = id => handle.nodes instanceof Map ? handle.nodes.get(id) : handle.nodes?.[id];
  const seen = new Set();
  const verifiedNodes = snapshot.requirements.requiredNodes.map(expected => {
    const node = nodeFor(expected.id);
    const type = ['Text', 'Graphics', 'Sprite', 'Mesh', 'Container'].find(name => PIXI[name] && node instanceof PIXI[name]);
    if (!node || seen.has(node) || type !== expected.type || !beneath(node, handle.root)) throw new Error(`missing, aliased or wrong native node: ${expected.id}`);
    seen.add(node);
    if (expected.edits.includes('text') && !(node instanceof PIXI.Text)) throw new Error('native Text required');
    return { ...expected, edits: [...expected.edits] };
  });
  const requested = snapshot.requirements.behaviorChecks.map(check => check.id).sort();
  if (canonical(Object.keys(behaviors).sort()) !== canonical(requested)) throw new Error('missing or unexpected requested behavior probes');
  const images = {};
  const readFrame = async key => {
    app.renderer.render(app.stage);
    const png = captureFrame ? await captureFrame(key) : app.canvas.toDataURL('image/png');
    if (!png.startsWith('data:image/png;base64,')) throw new Error('canvas readback failed');
    return png;
  };
  const capture = async key => { images[key] = await readFrame(key); };
  await capture('baseline');
  const resolution = app.renderer.resolution;
  if (!Number.isFinite(resolution) || resolution <= 0) throw new Error('invalid renderer resolution');
  const ids = new Map(verifiedNodes.map(expected => [nodeFor(expected.id), expected.id]));
  const provenanceNodes = [];
  for (const expected of verifiedNodes) {
    const node = nodeFor(expected.id);
    const measured = node.getBounds();
    const bounds = measured.rectangle ?? measured;
    if (!['x', 'y', 'width', 'height'].every(key => Number.isFinite(bounds[key]))) throw new Error(`invalid native bounds: ${expected.id}`);
    let ancestor = node.parent;
    while (ancestor && ancestor !== handle.root && !ids.has(ancestor)) ancestor = ancestor.parent;
    const parent = ids.get(ancestor) ?? null;
    const visibleAtBaseline = node.visible;
    let isolated, restored;
    try {
      node.visible = !visibleAtBaseline;
      isolated = await readFrame(`isolate-${expected.id}`);
    } finally {
      node.visible = visibleAtBaseline;
      restored = await readFrame(`isolate-${expected.id}-reset`);
    }
    provenanceNodes.push({
      id: expected.id, type: expected.type, parent, visibleAtBaseline,
      bounds: { x: bounds.x, y: bounds.y, width: bounds.width, height: bounds.height },
      isolation: { method: 'visibility-toggle', isolated, restored, restoredVisible: node.visible },
    });
  }
  for (const expected of verifiedNodes) {
    const node = nodeFor(expected.id);
    for (const edit of expected.edits) {
      const key = `edit-${expected.id}-${edit}`;
      const initial = { x: node.x, y: node.y, visible: node.visible, text: node.text };
      try {
        if (edit === 'position') node.position.set(node.x + Math.max(1, snapshot.artboard[0] * 0.05), node.y);
        else if (edit === 'visibility') node.visible = !node.visible;
        else if (edit === 'text') node.text = `${node.text} [edit probe]`;
        else throw new Error(`unsupported edit: ${edit}`);
        await capture(key);
      } finally {
        node.position.set(initial.x, initial.y);
        node.visible = initial.visible;
        if (edit === 'text') node.text = initial.text;
        await capture(`${key}-reset`);
      }
    }
  }
  for (const check of snapshot.requirements.behaviorChecks) {
    const probe = behaviors[check.id];
    if (typeof probe?.run !== 'function' || typeof probe?.reset !== 'function') throw new Error(`executable host behavior/reset required: ${check.id}`);
    try {
      await probe.run();
      await capture(`behavior-${check.id}`);
    } finally {
      await probe.reset();
      await capture(`behavior-${check.id}-reset`);
    }
  }
  const bytes = new TextEncoder().encode(canonical(snapshot));
  const hash = await crypto.subtle.digest('SHA-256', bytes);
  const snapshotSha256 = [...new Uint8Array(hash)].map(value => value.toString(16).padStart(2, '0')).join('');
  return {
    kind: 'img2.pixi2d-capture', version: 1, producer: 'pixi2d-native-capture-v2',
    snapshotSha256, renderer: 'pixi.js', pixiVersion: PIXI.VERSION,
    nodes: verifiedNodes, images,
    provenance: { contract: 'img2.pixi2d-node-provenance/v1', resolution, nodes: provenanceNodes },
  };
}
