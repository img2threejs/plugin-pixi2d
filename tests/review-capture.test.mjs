// Isolated unit doubles exercise the producer, NOT PixiJS/browser quality.
import test from 'node:test';
import assert from 'node:assert/strict';
import { webcrypto } from 'node:crypto';
import { captureEditableScene } from '../skills/img2pixi2d/runtime/review-capture.mjs';

if (!globalThis.crypto) globalThis.crypto = webcrypto;

class Container {
  constructor() {
    this.x = 0; this.y = 0; this.visible = true;
    this.position = { set: (x, y) => { this.x = x; this.y = y; } };
  }
  getBounds() { return { x: 0, y: 0, width: 3, height: 8 }; }
}
class Graphics extends Container {}
class Sprite extends Container {}
class Text extends Container { constructor() { super(); this.text = 'original'; } }
class Mesh extends Container {}
const PIXI = { Container, Graphics, Sprite, Text, Mesh, VERSION: '8.22.0' };

function fixture() {
  const stage = new Container();
  const root = new Container(); root.parent = stage;
  const badge = new Graphics(); badge.parent = root;
  const label = new Text(); label.parent = root;
  const nodes = new Map([['badge', badge], ['label', label]]);
  const app = {
    stage,
    renderer: { resolution: 1, render(target) { assert.equal(target, stage); } },
    canvas: {
      width: 8, height: 8,
      // Deliberately not actual PNG evidence; never passed to the harness gate.
      toDataURL() { return 'data:image/png;base64,' + Buffer.from(JSON.stringify([...nodes].map(([id, node]) => [id, node.x, node.y, node.visible, node.text]))).toString('base64'); },
    },
  };
  return {
    app, PIXI, handle: { root, nodes },
    snapshot: {
      kind: 'img2.pixi2d-snapshot', version: 1, artboard: [8, 8],
      requirements: {
        requiredNodes: [{ id: 'badge', type: 'Graphics', edits: ['position', 'visibility'] }, { id: 'label', type: 'Text', edits: ['text'] }],
        behaviorChecks: [],
      },
    },
  };
}

test('producer exercises native-handle edits and restores baseline', async () => {
  const input = fixture();
  const result = await captureEditableScene(input);
  assert.equal(result.producer, 'pixi2d-native-capture-v2');
  assert.equal(result.provenance.nodes.length, 2);
  assert.equal(result.provenance.nodes[0].isolation.restored, result.images.baseline);
  assert.match(result.snapshotSha256, /^[a-f0-9]{64}$/);
  assert.deepEqual(result.nodes, input.snapshot.requirements.requiredNodes);
  for (const key of ['edit-badge-position', 'edit-badge-visibility', 'edit-label-text']) {
    assert.notEqual(result.images[key], result.images.baseline);
    assert.equal(result.images[key + '-reset'], result.images.baseline);
  }
  assert.equal(input.handle.nodes.get('label').text, 'original');
});

test('plain objects and aliased nodes cannot masquerade as independent native nodes', async () => {
  const plain = fixture();
  plain.handle.nodes.set('badge', { x: 0, parent: plain.handle.root });
  await assert.rejects(captureEditableScene(plain), /native node/);
  const aliased = fixture();
  aliased.snapshot.requirements.requiredNodes[1] = { id: 'other', type: 'Graphics', edits: ['position'] };
  aliased.handle.nodes.set('other', aliased.handle.nodes.get('badge'));
  await assert.rejects(captureEditableScene(aliased), /aliased/);
});

test('scene outside the real host and wrong-size readback are refused', async () => {
  const detached = fixture(); detached.handle.root.parent = null;
  await assert.rejects(captureEditableScene(detached), /actual host/);
  const mismatch = fixture(); mismatch.app.canvas.width = 4;
  await assert.rejects(captureEditableScene(mismatch), /dimensions/);
});

test('every requested behavior needs executable run and reset callbacks', async () => {
  const input = fixture();
  input.snapshot.requirements.behaviorChecks = [{ id: 'end', changesPixels: true }];
  await assert.rejects(captureEditableScene(input), /missing or unexpected/);
  input.behaviors = { end: { run() {} } };
  await assert.rejects(captureEditableScene(input), /behavior\/reset/);
  const node = input.handle.nodes.get('badge');
  input.behaviors.end = { run() { node.x = 20; }, reset() { node.x = 0; } };
  const result = await captureEditableScene(input);
  assert.notEqual(result.images['behavior-end'], result.images.baseline);
  assert.equal(result.images['behavior-end-reset'], result.images.baseline);
});

test('mutations restore even when capture throws', async () => {
  const input = fixture();
  const original = input.app.canvas.toDataURL;
  let calls = 0;
  input.app.canvas.toDataURL = () => { if (++calls === 2) throw new Error('readback failed'); return original(); };
  await assert.rejects(captureEditableScene(input), /readback failed/);
  assert.equal(input.handle.nodes.get('badge').x, 0);
});
