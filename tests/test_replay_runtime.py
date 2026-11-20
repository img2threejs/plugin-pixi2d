"""Actual local Chromium/Pixi replay, never visual acceptance or native-node attestation.

Requires IMG2_TEST_HARNESS and PIXI_REPLAY_RUNTIME JSON with pixi-package,
playwright-package, chromium, chromium-root absolute paths. No installs/downloads.
Focused authorized reproduction: python3 tests/test_replay_runtime.py --reproduce
Verifier suite: python3 -m unittest discover -s tests -p test_replay_runtime.py -v
"""
import base64
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
AREA = Path('.img2/artifacts/pixi2d')
DRIVER = REPO / 'tools/replay-pixi2d.mjs'


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def reference_png():
    # Authored neutral protocol reference; NOT a claim that the fixture matches it.
    def chunk(tag, body):
        return struct.pack('>I', len(body)) + tag + body + struct.pack('>I', zlib.crc32(tag + body) & 0xffffffff)
    raw = (b'\0' + bytes((0, 0, 0, 0)) * 64) * 64
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 64, 64, 8, 6, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')


class ReplayFixture:
    def __init__(self, root, harness, runtime):
        self.root = Path(root)
        self.workspace = self.root / 'bound existing scene'
        self.workspace.mkdir()
        home = self.root / 'core home'
        home.mkdir()
        (home / 'harness').symlink_to(harness, target_is_directory=True)
        self.env = dict(os.environ, IMG2_HOME=str(home))
        self.runtime = runtime
        self.lock = self.root / 'independently-held-runtime-lock.json'
        self.put('reference.png', reference_png())
        for name in ('routed-scene.mjs', 'shape.mjs'):
            self.put('src/' + name, (REPO / 'tests/fixtures' / name).read_bytes())
        self.inputs = {
            'kind': 'img2.pixi2d-inputs', 'version': 1, 'objectId': 'real-pixi-regression',
            'reference': 'reference.png', 'spec': 'reconstruction.json', 'profile': 'profile.json',
            'sources': ['src/routed-scene.mjs', 'src/shape.mjs'], 'assets': [],
            'requiredNodes': [
                {'id': 'badge', 'type': 'Graphics', 'edits': ['position', 'visibility']},
                {'id': 'marker', 'type': 'Graphics', 'edits': ['visibility']},
            ],
            'criticalFeatures': [{'id': 'badge', 'bbox': [8, 8, 16, 16]}],
            'behaviorChecks': [
                {'id': 'motion-end', 'description': 'Actual fixture endpoint', 'changesPixels': True},
                {'id': 'lifecycle', 'description': 'Dispose/recreate while preserving a real shared Texture consumer', 'changesPixels': False},
            ],
            'replay': {'abi': 'img2.routed-pixi-scene/v1', 'entry': 'src/routed-scene.mjs', 'modules': ['src/routed-scene.mjs', 'src/shape.mjs'], 'assets': []},
        }
        self.put_json('reconstruction.json', {'fixture': 'real native Graphics replay; not a reconstruction-quality result'})
        self.put_json('profile.json', {'width': 64, 'height': 64, 'renderer': 'webgl', 'resolution': 1, 'antialias': False, 'background': 0, 'backgroundAlpha': 0})
        self.snapshot()

    def put(self, path, data):
        target = self.workspace / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def put_json(self, path, value):
        self.put(path, encoded(value))

    def snapshot(self):
        self.put_json(AREA / 'inputs.json', self.inputs)
        result = subprocess.run([sys.executable, str(REPO / 'tools/pixi2d.py'), 'snapshot', '--workspace', str(self.workspace)], env=self.env, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        self.current_snapshot = json.loads(result.stdout)

    def invoke(self, command, code=0):
        args = ['node', str(DRIVER), command]
        for key, value in self.runtime.items():
            args.extend(['--' + key, str(value)])
        if command != 'pins':
            args.extend(['--workspace', str(self.workspace), '--runtime-lock', str(self.lock)])
        result = subprocess.run(args, env=self.env, capture_output=True, text=True, timeout=180)
        if result.returncode != code:
            raise AssertionError(f'Expected exit {code}, got {result.returncode}: {result.stdout}\n{result.stderr}')
        return json.loads(result.stdout)

    def pin(self):
        self.lock.write_bytes(encoded(self.invoke('pins')))


def prerequisites():
    harness = os.environ.get('IMG2_TEST_HARNESS')
    runtime = os.environ.get('PIXI_REPLAY_RUNTIME')
    if not harness or not runtime:
        return None
    options = json.loads(runtime)
    expected = {'pixi-package', 'playwright-package', 'chromium', 'chromium-root'}
    if set(options) != expected or not (Path(harness) / 'img2_core/gate_runner.py').is_file():
        raise RuntimeError('Invalid explicit real-browser prerequisites')
    for path in options.values():
        if not Path(path).exists():
            raise RuntimeError('Missing real-browser prerequisite: ' + path)
    if not shutil.which('node'):
        raise RuntimeError('Node executable is required; never installed by this fixture')
    return Path(harness), options


class RealReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prerequisites = prerequisites()
        if cls.prerequisites is None:
            raise unittest.SkipTest('Real Chromium/Pixi prerequisites unavailable: set IMG2_TEST_HARNESS and PIXI_REPLAY_RUNTIME; no mock browser fallback')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pixi real replay ')
        self.addCleanup(self.temp.cleanup)
        self.fixture = ReplayFixture(self.temp.name, *self.prerequisites)
        self.fixture.pin()

    def test_real_esm_scene_runs_real_edits_resets_and_stays_nonauthoritative(self):
        result = self.fixture.invoke('capture')
        capture = result['replayCapture']
        self.assertFalse(result['terminalAcceptance'])
        self.assertEqual(result['nativeNodeProvenance'], 'unevaluated')
        self.assertFalse(capture['terminalAcceptance'])
        self.assertEqual(capture['producer'], 'pixi2d-cdp-replay-v1')
        self.assertEqual(capture['snapshotSha256'], hashlib.sha256(encoded(self.fixture.current_snapshot)).hexdigest())
        baseline = capture['images']['baseline']
        data = base64.b64decode(baseline.split(',', 1)[1])
        self.assertEqual(data[:8], b'\x89PNG\r\n\x1a\n')
        self.assertEqual(struct.unpack('>II', data[16:24]), (64, 64))
        for name in ('edit-badge-position', 'edit-badge-visibility', 'edit-marker-visibility', 'behavior-motion-end'):
            self.assertNotEqual(capture['images'][name], baseline)
            self.assertEqual(capture['images'][name + '-reset'], baseline)
        self.assertEqual(capture['images']['behavior-lifecycle'], baseline)
        self.assertFalse((self.fixture.workspace / AREA / 'capture.json').exists())
        self.assertFalse((self.fixture.workspace / AREA / 'artifact.json').exists())

    def test_live_replay_binds_saved_diagnostic_files_without_accepting_or_rewriting(self):
        result = self.fixture.invoke('capture')
        capture = result['replayCapture']
        # An explicitly unreviewed technical candidate, NOT a passed artifact/gate.
        self.fixture.put_json(AREA / 'capture.json', capture)
        self.fixture.put_json(AREA / 'artifact.json', {
            'kind': 'img2.pixi2d-scene', 'version': 1,
            'status': 'unreviewed-technical-fixture',
            'objectId': self.fixture.inputs['objectId'],
            'snapshotSha256': result['snapshotSha256'],
        })
        for name in ('evidence.json', 'review.json'):
            self.fixture.put_json(AREA / name, {'status': 'unreviewed-technical-fixture'})
        watched = ['snapshot.json', 'capture.json', 'artifact.json', 'evidence.json', 'review.json']
        before = {name: (self.fixture.workspace / AREA / name).read_bytes() for name in watched}
        replay = self.fixture.invoke('replay')
        self.assertTrue(replay['matchesSavedCapture'])
        self.assertEqual(replay['captureBinding']['sha256'], hashlib.sha256(before['capture.json']).hexdigest())
        self.assertEqual(replay['artifactBinding']['sha256'], hashlib.sha256(before['artifact.json']).hexdigest())
        self.assertEqual(replay['replayCaptureSha256'], hashlib.sha256(encoded(capture)).hexdigest())
        self.assertFalse(replay['terminalAcceptance'])
        self.assertEqual(replay['nativeNodeProvenance'], 'unevaluated')
        for name, data in before.items():
            self.assertEqual((self.fixture.workspace / AREA / name).read_bytes(), data)

    def test_page_controlled_to_data_url_is_not_capture_authority(self):
        path = self.fixture.workspace / self.fixture.inputs['replay']['entry']
        path.write_text(path.read_text().replace("if (Object.keys(assets)", "app.canvas.toDataURL = () => { throw new Error('page-controlled-forgery'); };\n  if (Object.keys(assets)"))
        self.fixture.snapshot()
        capture = self.fixture.invoke('capture')['replayCapture']
        self.assertTrue(base64.b64decode(capture['images']['baseline'].split(',', 1)[1]).startswith(b'\x89PNG'))
        self.assertFalse(capture['terminalAcceptance'])

    def test_unbound_executable_dependency_is_refused_without_substitution(self):
        self.fixture.inputs['replay']['modules'].remove('src/shape.mjs')
        self.fixture.snapshot()
        result = self.fixture.invoke('capture', 2)
        self.assertEqual(result['status'], 'blocked')
        self.assertFalse(result['terminalAcceptance'])

    def test_arbitrary_network_import_is_refused(self):
        path = self.fixture.workspace / self.fixture.inputs['replay']['entry']
        path.write_text("import 'https://example.invalid/not-allowed.mjs';\n" + path.read_text())
        self.fixture.snapshot()
        result = self.fixture.invoke('capture', 2)
        self.assertEqual(result['status'], 'blocked')

    def test_missing_real_behavior_callback_blocks(self):
        path = self.fixture.workspace / self.fixture.inputs['replay']['entry']
        path.write_text(path.read_text().replace("'motion-end': {", "'wrong-behavior': {"))
        self.fixture.snapshot()
        result = self.fixture.invoke('capture', 2)
        self.assertTrue(any('missing or unexpected' in reason for reason in result['reasons']))

    def test_changed_source_or_runtime_lock_blocks_before_running(self):
        path = self.fixture.workspace / 'src/shape.mjs'
        path.write_text(path.read_text() + '\n// changed after snapshot\n')
        result = self.fixture.invoke('capture', 2)
        self.assertTrue(any('stale-snapshot' in reason for reason in result['reasons']))
        self.fixture.snapshot()
        lock = json.loads(self.fixture.lock.read_text())
        lock['pixi']['version'] = '0.0.0'
        self.fixture.lock.write_bytes(encoded(lock))
        result = self.fixture.invoke('capture', 2)
        self.assertIn('runtime-pin-mismatch', result['reasons'])

    def test_unsupported_original_host_has_no_fake_factory_fallback(self):
        path = self.fixture.workspace / self.fixture.inputs['replay']['entry']
        path.write_text('export const hostSpecificSource = true;\n')
        self.fixture.snapshot()
        result = self.fixture.invoke('capture', 2)
        self.assertTrue(any('createRoutedPixiScene-export-required' in reason for reason in result['reasons']))


if __name__ == '__main__':
    if sys.argv[1:] == ['--reproduce']:
        required = prerequisites()
        if required is None:
            raise SystemExit('Explicit real-browser prerequisites missing; no synthetic substitute')
        with tempfile.TemporaryDirectory(prefix='pixi authorized reproduction ') as directory:
            fixture = ReplayFixture(directory, *required)
            fixture.pin()
            result = fixture.invoke('capture')
            capture = result['replayCapture']
            images = capture['images']
            print(json.dumps({
                'observation': 'Actual pinned local Pixi/Chromium CDP replay, not acceptance',
                'browserVersion': result['browserVersion'], 'pixiVersion': capture['pixiVersion'],
                'snapshotSha256': result['snapshotSha256'], 'replayCaptureSha256': result['replayCaptureSha256'],
                'frameCount': len(images), 'positionChangesPixels': images['baseline'] != images['edit-badge-position'],
                'positionResetMatches': images['baseline'] == images['edit-badge-position-reset'],
                'lifecycleMatches': images['baseline'] == images['behavior-lifecycle'],
                'nativeNodeProvenance': result['nativeNodeProvenance'], 'terminalAcceptance': result['terminalAcceptance'],
            }, sort_keys=True))
    else:
        unittest.main()
