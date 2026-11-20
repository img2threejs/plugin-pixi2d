"""Offline protocol fixtures, NOT real artwork, native vision or browser-quality evidence.

IMG2_TEST_HARNESS=/path/to/img2 python3 -m unittest discover -s tests -v
The actual harness runner is used; no installed registry or host links are modified.
"""
import base64
import copy
import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
AREA = Path('.img2/artifacts/pixi2d')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def fixture_png(changed=False, width=8, height=8):
    def chunk(tag, body):
        return struct.pack('>I', len(body)) + tag + body + struct.pack('>I', zlib.crc32(tag + body) & 0xffffffff)
    raw = b''.join(b'\0' + b''.join(bytes((255 if changed and x < 3 else 20, y * 20, x * 20, 255)) for x in range(width)) for y in range(height))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')


class HarnessReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        harness = os.environ.get('IMG2_TEST_HARNESS')
        if not harness:
            raise unittest.SkipTest('Set IMG2_TEST_HARNESS to the read-only img2 checkout; no installed harness is assumed')
        cls.harness = Path(harness).resolve()
        if not (cls.harness / 'img2_core' / 'gate_runner.py').is_file():
            raise RuntimeError('IMG2_TEST_HARNESS does not contain the real gate runner')

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='pixi2d harness ')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.workspace = self.root / 'existing host'
        self.workspace.mkdir()
        home = self.root / 'isolated home'
        home.mkdir()
        (home / 'harness').symlink_to(self.harness, target_is_directory=True)
        self.env = dict(os.environ, IMG2_HOME=str(home), PYTHONPATH=str(self.harness))
        self.inputs = {
            'kind': 'img2.pixi2d-inputs', 'version': 1, 'objectId': 'whole-image',
            'reference': '.img2pixi2d/reference/working.png',
            'spec': '.img2pixi2d/reconstruction.json', 'profile': '.img2pixi2d/profile.json',
            'sources': ['src/subject.ts'], 'assets': [],
            'requiredNodes': [{'id': 'badge', 'type': 'Graphics', 'edits': ['position', 'visibility']}],
            'criticalFeatures': [{'id': 'mark', 'bbox': [0, 0, 4, 4]}],
            'behaviorChecks': [
                {'id': 'motion-extremum', 'description': 'Fixture behavior only; not a real requested motion review', 'changesPixels': True},
                {'id': 'lifecycle', 'description': 'Fixture of required disposal/recreation evidence', 'changesPixels': False},
            ],
            'scopedCandidates': {'build-strategy': [{'id': 'native', 'operations': ['graphics'], 'componentIds': ['badge'], 'specFields': ['components.badge'], 'prerequisites': [], 'expectedMeasurements': ['independent-position']}], 'repair': []},
        }
        self.put(self.inputs['reference'], fixture_png())
        self.put('src/subject.ts', b'// Deliberately NOT a runtime fixture: source text alone cannot pass.\nexport const example = 1;\n')
        self.put_json(self.inputs['spec'], {'components': [{'id': 'badge', 'representation': 'Graphics'}]})
        self.put_json(self.inputs['profile'], {'width': 8, 'height': 8, 'state': 'neutral'})
        self.put_json(str(AREA / 'inputs.json'), self.inputs)

    def put(self, relative, content):
        path = self.workspace / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def put_json(self, relative, value):
        self.put(relative, canonical(value))

    def get(self, name):
        return json.loads((self.workspace / AREA / name).read_text())

    def cli(self, command, code=0):
        result = subprocess.run([sys.executable, str(REPO / 'tools/pixi2d.py'), command, '--workspace', str(self.workspace)], cwd=self.workspace, env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def runner(self, code):
        result = subprocess.run([sys.executable, '-m', 'img2_core.gate_runner', '--plugin-dir', str(REPO), '--workspace', str(self.workspace)], env=self.env, cwd=self.workspace, capture_output=True, text=True)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        envelope = json.loads(result.stdout)
        self.assertEqual(envelope['kind'], 'img2.gate-run')
        self.assertEqual(envelope['stopped'], code != 0)
        self.assertEqual(envelope['results'][0]['blocking'], True)
        return envelope

    def captured(self):
        snapshot = self.cli('snapshot')
        url = lambda data: 'data:image/png;base64,' + base64.b64encode(data).decode()
        images = {'baseline': url(fixture_png())}
        for name in ('edit-badge-position', 'edit-badge-visibility', 'behavior-motion-extremum'):
            images[name] = url(fixture_png(True))
            images[name + '-reset'] = images['baseline']
        images['behavior-lifecycle'] = images['baseline']
        images['behavior-lifecycle-reset'] = images['baseline']
        capture = {'kind': 'img2.pixi2d-capture', 'version': 1, 'producer': 'pixi2d-native-capture-v1', 'snapshotSha256': sha(canonical(snapshot)), 'renderer': 'pixi.js', 'pixiVersion': '8.22.0', 'nodes': snapshot['requirements']['requiredNodes'], 'images': images}
        self.put_json(str(AREA / 'capture.json'), capture)
        return snapshot, capture

    def reviewed(self):
        snapshot, capture = self.captured()
        evidence = self.cli('produce')
        paths = [item['path'] for item in evidence['files']]
        review = {'kind': 'img2.pixi2d-review', 'version': 1, 'snapshotSha256': sha(canonical(snapshot)), 'evidenceSha256': sha(canonical(evidence)), 'reviewer': {'id': 'synthetic-unit-fixture-not-native-vision', 'method': 'native-vision'}, 'unresolvedDefects': [], 'inspected': snapshot['bindings'] + evidence['files'], 'assessments': [{'id': check, 'judgment': 'pass', 'score': 3, 'reason': 'Synthetic protocol fixture; no real visual-quality claim.', 'evidence': paths} for check in snapshot['checks']]}
        self.put_json(str(AREA / 'review.json'), review)
        return snapshot, capture, evidence, review

    def test_complete_protocol_publishes_editable_2d_and_real_runner_passes(self):
        snapshot, _, evidence, _ = self.reviewed()
        artifact = self.cli('publish')
        self.assertEqual(artifact['outputKind'], '2d-scene')
        self.assertEqual(artifact['coordinates']['units'], 'reference-pixels')
        self.assertNotIn('scaleEstimate', artifact)
        self.assertEqual(artifact['editableSources'][0]['path'], 'src/subject.ts')
        self.assertEqual(snapshot['scopedCandidates']['build-strategy'][0]['id'], 'native')
        crops = [entry for entry in evidence['files'] if 'feature-mark-' in entry['path']]
        self.assertEqual(len(crops), 2)
        for entry in crops:
            data = (self.workspace / entry['path']).read_bytes()
            self.assertEqual(data, fixture_png(width=4, height=4))
            self.assertEqual(sha(data), entry['sha256'])
        self.assertEqual(self.runner(0)['results'][0]['status'], 'pass')

    def test_source_and_passing_prose_without_runtime_evidence_cannot_pass(self):
        self.cli('snapshot')
        self.put_json(str(AREA / 'review.json'), {'decision': 'continue', 'review': 'looks great'})
        self.assertEqual(self.runner(1)['results'][0]['status'], 'fail')
        self.assertFalse((self.workspace / AREA / 'artifact.json').exists())

    def test_produced_captures_without_review_block(self):
        self.captured()
        self.cli('produce')
        self.cli('publish', 2)
        self.runner(1)

    def test_missing_uncertain_or_failed_required_assessment_blocks(self):
        _, _, _, review = self.reviewed()
        original = copy.deepcopy(review)
        for mutation in ('missing', 'uncertain', 'failed', 'low-score', 'no-evidence', 'no-crops', 'no-reviewer', 'defect'):
            with self.subTest(mutation=mutation):
                review = copy.deepcopy(original)
                critical = next(item for item in review['assessments'] if item['id'] == 'feature:mark')
                if mutation == 'missing': review['assessments'].remove(critical)
                elif mutation == 'uncertain': critical['judgment'] = 'uncertain'
                elif mutation == 'failed': critical['judgment'] = 'fail'
                elif mutation == 'low-score': critical['score'] = 2
                elif mutation == 'no-evidence': critical['evidence'] = []
                elif mutation == 'no-crops': critical['evidence'] = [path for path in critical['evidence'] if 'feature-' not in path]
                elif mutation == 'no-reviewer': review['reviewer']['method'] = 'source-text'
                elif mutation == 'defect': review['unresolvedDefects'] = ['missing mark']
                self.put_json(str(AREA / 'review.json'), review)
                self.cli('publish', 2)
                self.runner(1)

    def test_source_asset_plan_profile_and_reference_changes_invalidate(self):
        self.inputs['assets'] = ['art/license.txt']
        self.put('art/license.txt', b'User retains ownership')
        self.put_json(str(AREA / 'inputs.json'), self.inputs)
        self.reviewed()
        self.cli('publish')
        for path in ('src/subject.ts', 'art/license.txt', self.inputs['spec'], self.inputs['profile'], self.inputs['reference']):
            with self.subTest(path=path):
                original = (self.workspace / path).read_bytes()
                self.put(path, original + b' ')
                self.runner(1)
                self.put(path, original)

    def test_missing_unchanged_reset_mismatched_and_text_only_captures_block(self):
        _, capture = self.captured()
        original = copy.deepcopy(capture)
        for mutation in ('missing', 'unchanged', 'reset', 'size', 'text', 'runtime-node'):
            with self.subTest(mutation=mutation):
                capture = copy.deepcopy(original)
                key = 'edit-badge-position'
                if mutation == 'missing': del capture['images'][key]
                elif mutation == 'unchanged': capture['images'][key] = capture['images']['baseline']
                elif mutation == 'reset': capture['images'][key + '-reset'] = capture['images'][key]
                elif mutation == 'size': capture['images'][key] = 'data:image/png;base64,' + base64.b64encode(fixture_png(True, 4, 8)).decode()
                elif mutation == 'text': capture['images'][key] = 'data:image/png;base64,' + base64.b64encode(b'export const accepted = true').decode()
                elif mutation == 'runtime-node': capture['nodes'][0]['type'] = 'Sprite'
                self.put_json(str(AREA / 'capture.json'), capture)
                self.cli('produce', 2)
                self.runner(1)

    def test_changed_or_missing_published_evidence_blocks_after_acceptance(self):
        _, _, evidence, _ = self.reviewed()
        self.cli('publish')
        victim = self.workspace / evidence['files'][0]['path']
        victim.write_bytes(b'not a canvas')
        self.runner(1)

    def test_non_atomic_full_image_sprite_is_refused(self):
        self.inputs['requiredNodes'][0]['type'] = 'Sprite'
        self.put_json(str(AREA / 'inputs.json'), self.inputs)
        self.assertIn('raster-only-scene-refused', self.cli('snapshot', 2)['reasons'])

    def test_source_paths_cannot_escape_workspace(self):
        outside = self.root / 'outside.ts'
        outside.write_text('export const unsafe = true')
        self.inputs['sources'] = ['../outside.ts']
        self.put_json(str(AREA / 'inputs.json'), self.inputs)
        self.cli('snapshot', 2)
        self.runner(1)

    def test_artifact_is_required_and_revalidated_by_gate(self):
        self.reviewed()
        self.runner(1)
        artifact = self.cli('publish')
        artifact['editableSources'] = []
        self.put_json(str(AREA / 'artifact.json'), artifact)
        self.runner(1)

    def test_lifecycle_observation_cannot_be_omitted(self):
        self.inputs['behaviorChecks'] = []
        self.put_json(str(AREA / 'inputs.json'), self.inputs)
        self.assertIn('dispose-recreate-behavior-required', self.cli('snapshot', 2)['reasons'])
        self.runner(1)

    def test_candidates_cannot_introduce_commands_or_foreign_components(self):
        original = copy.deepcopy(self.inputs)
        for mutation in ('command', 'component', 'operation'):
            with self.subTest(mutation=mutation):
                inputs = copy.deepcopy(original)
                candidate = inputs['scopedCandidates']['build-strategy'][0]
                if mutation == 'command': candidate['argv'] = ['sh', 'unapproved']
                elif mutation == 'component': candidate['componentIds'] = ['foreign']
                else: candidate['operations'] = ['install-provider']
                self.put_json(str(AREA / 'inputs.json'), inputs)
                self.cli('snapshot', 2)

    def test_route_card_is_explicitly_2d_not_a_3d_terminal_kind(self):
        card = json.loads((REPO / 'route.json').read_text())
        manifest = json.loads((REPO / 'plugin.json').read_text())
        self.assertEqual(card['outputKind'], '2d-scene')
        self.assertEqual(manifest['capabilities'], [{'from': 'image', 'to': 'pixi2d-scene'}])


if __name__ == '__main__':
    unittest.main()
