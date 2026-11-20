#!/usr/bin/env node
/** Offline, disposable ESM replay. Actual CDP pixels, NOT native-node or terminal authority. */
import { createHash, randomBytes } from 'node:crypto';
import { readFile, readdir, realpath, lstat } from 'node:fs/promises';
import { createReadStream } from 'node:fs';
import { dirname, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';
import { platform, release, arch } from 'node:os';

const HERE = dirname(fileURLToPath(import.meta.url));
const PLUGIN = resolve(HERE, '..');
const AREA = '.img2/artifacts/pixi2d/';
const PIXI_VERSION = '8.22.0';
const PLAYWRIGHT_VERSION = '1.64.0';
const fail = reason => { throw new Error(reason); };
const requireValue = (ok, reason) => { if (!ok) fail(reason); };
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const canonical = value => {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object') return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}`;
  if (typeof value === 'number' && !Number.isFinite(value)) fail('non-finite-json');
  const encoded = JSON.stringify(value);
  requireValue(encoded !== undefined, 'non-json-value');
  return encoded;
};
const jsonFile = async path => JSON.parse(await readFile(path, 'utf8'));
const under = (root, target) => target === root || target.startsWith(root + sep);
const fileHash = async path => {
  const hash = createHash('sha256');
  for await (const chunk of createReadStream(path)) hash.update(chunk);
  return hash.digest('hex');
};

async function tree(root) {
  const files = [];
  async function visit(directory) {
    const entries = await readdir(directory, { withFileTypes: true });
    entries.sort((a, b) => a.name.localeCompare(b.name, 'en'));
    for (const entry of entries) {
      const path = join(directory, entry.name);
      const name = relative(root, path).split(sep).join('/');
      if (entry.isSymbolicLink()) {
        const target = await realpath(path);
        requireValue(under(root, target), `runtime-symlink-escapes:${name}`);
        files.push({ path: name, symlink: relative(root, target).split(sep).join('/') });
      } else if (entry.isDirectory()) await visit(path);
      else if (entry.isFile()) files.push({ path: name, sha256: await fileHash(path) });
      else fail(`unsupported-runtime-file:${name}`);
    }
  }
  await visit(root);
  return files;
}

async function runtimeFacts(args) {
  const pixi = await realpath(args['pixi-package']);
  const playwright = await realpath(args['playwright-package']);
  const chromium = await realpath(args.chromium);
  const browserRoot = await realpath(args['chromium-root']);
  requireValue(under(browserRoot, chromium), 'chromium-outside-pinned-bundle');
  requireValue((await lstat(chromium)).isFile(), 'chromium-executable-required');
  const pixiPackage = await jsonFile(join(pixi, 'package.json'));
  const playwrightPackage = await jsonFile(join(playwright, 'package.json'));
  requireValue(pixiPackage.name === 'pixi.js' && pixiPackage.version === PIXI_VERSION, `pixi-version-required:${PIXI_VERSION}`);
  requireValue(playwrightPackage.name === 'playwright' && playwrightPackage.version === PLAYWRIGHT_VERSION, `playwright-version-required:${PLAYWRIGHT_VERSION}`);
  const resolveDependency = createRequire(join(playwright, 'package.json'));
  const core = dirname(resolveDependency.resolve('playwright-core/package.json'));
  requireValue((await jsonFile(join(core, 'package.json'))).version === PLAYWRIGHT_VERSION, 'playwright-core-version-mismatch');
  const producerFiles = ['tools/replay-pixi2d.mjs', 'skills/img2pixi2d/runtime/replay-host.mjs', 'skills/img2pixi2d/runtime/review-capture.mjs'];
  return {
    kind: 'img2.pixi2d-replay-runtime-lock', version: 1,
    platform: { os: platform(), release: release(), arch: arch() },
    node: { path: await realpath(process.execPath), version: process.version, sha256: await fileHash(process.execPath) },
    pixi: { path: pixi, version: PIXI_VERSION, files: await tree(pixi) },
    playwright: { path: playwright, version: PLAYWRIGHT_VERSION, files: await tree(playwright) },
    playwrightCore: { path: core, version: PLAYWRIGHT_VERSION, files: await tree(core) },
    chromium: { path: chromium, root: browserRoot, files: await tree(browserRoot) },
    producer: await Promise.all(producerFiles.map(async path => ({ path, sha256: await fileHash(join(PLUGIN, path)) }))),
  };
}

async function workspaceFile(workspace, name) {
  requireValue(typeof name === 'string' && name && !name.includes('\\') && !name.startsWith('/'), 'workspace-relative-path-required');
  const path = await realpath(resolve(workspace, name));
  requireValue(under(workspace, path) && relative(workspace, path).split(sep).join('/') === name, 'noncanonical-or-escaping-workspace-path');
  requireValue((await lstat(path)).isFile(), `file-required:${name}`);
  return { path: name, bytes: await readFile(path) };
}

async function boundWorkspace(workspace, mode) {
  const snapshotFile = await workspaceFile(workspace, AREA + 'snapshot.json');
  const snapshot = JSON.parse(snapshotFile.bytes);
  requireValue(snapshot.kind === 'img2.pixi2d-snapshot' && snapshot.version === 1, 'invalid-snapshot');
  requireValue(Array.isArray(snapshot.bindings) && snapshot.bindings.length > 0, 'snapshot-bindings-required');
  const files = new Map();
  for (const binding of snapshot.bindings) {
    requireValue(!files.has(binding.path), 'duplicate-snapshot-binding');
    const file = await workspaceFile(workspace, binding.path);
    requireValue(sha(file.bytes) === binding.sha256, `stale-snapshot:${binding.path}`);
    files.set(binding.path, file.bytes);
  }
  requireValue(files.has(AREA + 'inputs.json'), 'inputs-not-bound');
  const inputs = JSON.parse(files.get(AREA + 'inputs.json'));
  const replay = inputs.replay;
  requireValue(replay?.abi === 'img2.routed-pixi-scene/v1', 'explicit-routed-pixi-esm-abi-required');
  requireValue(canonical(snapshot.replay) === canonical(replay), 'replay-not-frozen-in-snapshot');
  requireValue(inputs.objectId === snapshot.objectId, 'foreign-snapshot-object');
  requireValue(canonical(snapshot.requirements) === canonical(Object.fromEntries(['requiredNodes', 'criticalFeatures', 'behaviorChecks'].map(key => [key, inputs[key]]))), 'requirements-not-bound');
  requireValue(Array.isArray(replay.modules) && replay.modules.length > 0 && new Set(replay.modules).size === replay.modules.length && replay.modules.includes(replay.entry), 'explicit-module-closure-required');
  requireValue(Array.isArray(inputs.sources) && Array.isArray(inputs.assets), 'source-and-asset-manifests-required');
  const sources = inputs.sources.map(path => {
    requireValue(files.has(path), `source-not-bound:${path}`);
    return { path, sha256: sha(files.get(path)) };
  });
  for (const path of replay.modules) {
    requireValue(inputs.sources.includes(path) && files.has(path), `executable-source-not-bound:${path}`);
    requireValue(/\.(?:m?js)$/.test(path), `unsupported-typescript-or-module-format:${path}`);
  }
  requireValue(Array.isArray(replay.assets), 'explicit-runtime-assets-required');
  const aliases = new Set();
  for (const asset of replay.assets) {
    requireValue(inputs.assets.includes(asset.path) && files.has(asset.path), `runtime-asset-not-bound:${asset.path}`);
    requireValue(typeof asset.alias === 'string' && /^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$/.test(asset.alias) && !aliases.has(asset.alias), 'invalid-or-duplicate-asset-alias');
    aliases.add(asset.alias);
    requireValue(['texture', 'font', 'json', 'bytes'].includes(asset.type), 'unsupported-asset-loader');
  }
  const profile = JSON.parse(files.get(inputs.profile) ?? fail('profile-not-bound'));
  requireValue(Number.isInteger(profile.width) && Number.isInteger(profile.height) && profile.width > 0 && profile.height > 0 && profile.width <= 8192 && profile.height <= 8192 && profile.width * profile.height <= 32_000_000, 'invalid-profile-size');
  requireValue(canonical(snapshot.artboard) === canonical([profile.width, profile.height]), 'profile-artboard-mismatch');
  requireValue(profile.renderer === 'webgl' && profile.resolution === 1 && typeof profile.antialias === 'boolean' && Number.isInteger(profile.background) && profile.background >= 0 && profile.background <= 0xffffff && Number.isFinite(profile.backgroundAlpha) && profile.backgroundAlpha >= 0 && profile.backgroundAlpha <= 1, 'explicit-webgl-resolution1-render-profile-required');
  const assets = inputs.assets.map(path => {
    requireValue(files.has(path), `asset-not-bound:${path}`);
    return { path, sha256: sha(files.get(path)) };
  });
  const saved = {};
  for (const [key, name] of [['captureBinding', 'capture.json'], ['artifactBinding', 'artifact.json']]) {
    if (mode === 'replay') {
      const file = await workspaceFile(workspace, AREA + name);
      saved[key] = { path: file.path, sha256: sha(file.bytes) };
      saved[key === 'captureBinding' ? 'capture' : 'artifact'] = JSON.parse(file.bytes);
    } else saved[key] = null;
  }
  const snapshotSha256 = sha(canonical(snapshot));
  if (mode === 'replay') {
    requireValue(saved.capture.snapshotSha256 === snapshotSha256 && saved.artifact.snapshotSha256 === snapshotSha256 && saved.artifact.objectId === snapshot.objectId, 'saved-artifact-or-capture-not-current');
  }
  return { workspace, snapshot, snapshotSha256, inputs, replay, profile, files, sources, assets, saved, snapshotBinding: { path: snapshotFile.path, sha256: sha(snapshotFile.bytes) } };
}

function expectedFrames(snapshot) {
  const frames = ['baseline'];
  for (const node of snapshot.requirements.requiredNodes) for (const edit of node.edits) frames.push(`edit-${node.id}-${edit}`, `edit-${node.id}-${edit}-reset`);
  for (const behavior of snapshot.requirements.behaviorChecks) frames.push(`behavior-${behavior.id}`, `behavior-${behavior.id}-reset`);
  requireValue(new Set(frames).size === frames.length, 'ambiguous-capture-state-ids');
  return frames;
}

async function replayScene(state, runtime) {
  const { chromium } = await import(pathToFileURL(join(runtime.playwright.path, 'index.mjs')).href);
  const browser = await chromium.launch({
    executablePath: runtime.chromium.path, headless: true, chromiumSandbox: true, timeout: 30000,
    ignoreDefaultArgs: ['--headless'],
    args: ['--headless=new', '--enable-automation', '--use-angle=swiftshader', '--disable-domain-reliability', '--disable-quic',
      '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1', '--proxy-server=http://127.0.0.1:9', '--proxy-bypass-list=127.0.0.1'],
  });
  try {
    const browserSession = await browser.newBrowserCDPSession();
    const browserCommandLine = await browserSession.send('Browser.getBrowserCommandLine');
    const { width, height } = state.profile;
    const context = await browser.newContext({ viewport: { width, height }, screen: { width, height }, deviceScaleFactor: 1, serviceWorkers: 'block', acceptDownloads: false, locale: 'en-US', timezoneId: 'UTC', colorScheme: 'light', reducedMotion: 'no-preference' });
    const origin = 'http://127.0.0.1:18888';
    const nonce = randomBytes(32).toString('hex');
    const hostTemplate = await readFile(join(PLUGIN, 'skills/img2pixi2d/runtime/replay-host.mjs'), 'utf8');
    const config = { nonce, snapshot: state.snapshot, entry: '/workspace/' + state.replay.entry, assets: state.replay.assets, profile: state.profile };
    const host = Buffer.from('const CONFIG = ' + canonical(config) + ';\n' + hostTemplate);
    const importMap = canonical({ imports: { 'pixi.js': '/runtime/pixi.mjs' } });
    const html = Buffer.from(`<!doctype html><meta charset="utf-8"><script type="importmap">${importMap}</script><script type="module" src="/runtime/host.mjs"></script>`);
    const csp = `default-src 'none'; script-src 'self' 'sha256-${createHash('sha256').update(importMap).digest('base64')}'; connect-src 'self'; img-src 'self' blob:; font-src 'self'; style-src 'unsafe-inline'; worker-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'`;
    const routes = new Map([
      ['/', { bytes: html, type: 'text/html', kinds: ['document'] }],
      ['/runtime/host.mjs', { bytes: host, type: 'text/javascript', kinds: ['script'] }],
      ['/runtime/pixi.mjs', { bytes: await readFile(join(runtime.pixi.path, 'dist/pixi.min.mjs')), type: 'text/javascript', kinds: ['script'] }],
      ['/runtime/unsafe-eval.js', { bytes: await readFile(join(runtime.pixi.path, 'dist/packages/unsafe-eval.min.js')), type: 'text/javascript', kinds: ['script'] }],
      ['/runtime/review-capture.mjs', { bytes: await readFile(join(PLUGIN, 'skills/img2pixi2d/runtime/review-capture.mjs')), type: 'text/javascript', kinds: ['script'] }],
    ]);
    for (const path of state.replay.modules) routes.set('/workspace/' + path, { bytes: state.files.get(path), type: 'text/javascript', kinds: ['script'] });
    const mime = path => /\.png$/i.test(path) ? 'image/png' : /\.jpe?g$/i.test(path) ? 'image/jpeg' : /\.webp$/i.test(path) ? 'image/webp' : /\.svg$/i.test(path) ? 'image/svg+xml' : /\.json$/i.test(path) ? 'application/json' : /\.woff2?$/i.test(path) ? 'font/woff2' : /\.otf$/i.test(path) ? 'font/otf' : /\.ttf$/i.test(path) ? 'font/ttf' : 'application/octet-stream';
    for (const asset of state.replay.assets) routes.set('/workspace/' + asset.path, { bytes: state.files.get(asset.path), type: mime(asset.path), kinds: ['image', 'font', 'fetch', 'xhr'] });
    const violations = [];
    const loadedResources = [];
    await context.route('**/*', async route => {
      const request = route.request();
      const url = new URL(request.url());
      const resource = url.origin === origin && !url.search && !url.hash && !url.username && !url.password ? routes.get(url.pathname) : null;
      if (request.method() !== 'GET' || !resource || !resource.kinds.includes(request.resourceType())) {
        violations.push({ reason: 'unapproved-resource', url: request.url(), resourceType: request.resourceType() });
        await route.abort('blockedbyclient');
        return;
      }
      await route.fulfill({ status: 200, body: resource.bytes, contentType: resource.type, headers: { 'Content-Security-Policy': csp, 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' } });
      loadedResources.push({ path: url.pathname, resourceType: request.resourceType(), sha256: sha(resource.bytes) });
    });
    await context.routeWebSocket('**/*', socket => { violations.push({ reason: 'websocket-forbidden' }); socket.close(); });
    context.on('page', page => { if (context.pages().length > 1) { violations.push({ reason: 'popup-forbidden' }); void page.close(); } });
    const page = await context.newPage();
    const cdp = await context.newCDPSession(page);
    await cdp.send('DOM.enable');
    const frames = expectedFrames(state.snapshot);
    const images = {};
    let frameIndex = 0;
    const pageErrors = [];
    page.on('pageerror', error => pageErrors.push(error.message));
    await page.exposeBinding('__pixiReplayViolation', ({ page: caller }, token, blockedURI, directive) => {
      requireValue(caller === page && token === nonce, 'unexpected-policy-report');
      violations.push({ reason: 'content-security-policy', blockedURI, directive });
    });
    await page.exposeBinding('__pixiReplayFrame', async ({ page: caller }, token, key) => {
      requireValue(caller === page && token === nonce && frames[frameIndex] === key, 'unexpected-external-capture-request');
      requireValue(violations.length === 0, 'unapproved-resource-requested');
      const { root } = await cdp.send('DOM.getDocument', { depth: 2 });
      const { nodeIds } = await cdp.send('DOM.querySelectorAll', { nodeId: root.nodeId, selector: 'body > canvas' });
      requireValue(nodeIds.length === 1, 'single-host-canvas-required');
      const { attributes } = await cdp.send('DOM.getAttributes', { nodeId: nodeIds[0] });
      const attributesMap = {};
      for (let index = 0; index < attributes.length; index += 2) attributesMap[attributes[index]] = attributes[index + 1];
      requireValue(attributesMap.width === String(width) && attributesMap.height === String(height), 'actual-canvas-dimensions-mismatch');
      // Browser/CDP rasterization from outside the page, never page-controlled toDataURL.
      const screenshot = await page.screenshot({ type: 'png', fullPage: false, omitBackground: true, scale: 'css', timeout: 15000 });
      images[key] = 'data:image/png;base64,' + screenshot.toString('base64');
      frameIndex++;
      return images[key];
    });
    await page.goto(origin + '/', { waitUntil: 'domcontentloaded', timeout: 30000 });
    const status = await page.waitForFunction(() => globalThis.__pixiReplayFinished, undefined, { timeout: 60000 });
    const observed = await status.jsonValue();
    requireValue(violations.length === 0, `unapproved-resource-requested:${canonical(violations)}`);
    requireValue(pageErrors.length === 0, `browser-runtime-error:${pageErrors.join(';')}`);
    requireValue(observed?.ok === true, `scene-replay-failed:${observed?.error ?? 'unknown'}`);
    requireValue(frameIndex === frames.length && canonical(Object.keys(images)) === canonical(frames), 'incomplete-external-capture');
    for (const node of state.snapshot.requirements.requiredNodes) for (const edit of node.edits) {
      const key = `edit-${node.id}-${edit}`;
      requireValue(images[key] !== images.baseline, `edit-has-no-visible-effect:${key}`);
      requireValue(images[`${key}-reset`] === images.baseline, `reset-capture-mismatch:${key}`);
    }
    for (const behavior of state.snapshot.requirements.behaviorChecks) {
      const key = `behavior-${behavior.id}`;
      if (behavior.changesPixels) requireValue(images[key] !== images.baseline, `behavior-has-no-visible-effect:${key}`);
      requireValue(images[`${key}-reset`] === images.baseline, `reset-capture-mismatch:${key}`);
    }
    const replayCapture = {
      kind: 'img2.pixi2d-capture', version: 1, producer: 'pixi2d-cdp-replay-v1',
      snapshotSha256: state.snapshotSha256, renderer: 'pixi.js', pixiVersion: PIXI_VERSION,
      nodes: state.snapshot.requirements.requiredNodes, images,
      nativeNodeProvenance: 'unevaluated', terminalAcceptance: false,
    };
    return { replayCapture, browserVersion: browser.version(), browserCommandLine: browserCommandLine.arguments, renderedHostSha256: sha(host), loadedResources, approvedRuntimeRequests: [...routes].map(([path, value]) => ({ path, sha256: sha(value.bytes) })) };
  } finally {
    await browser.close();
  }
}

function parseArgs(argv) {
  const command = argv.shift();
  requireValue(['pins', 'capture', 'replay'].includes(command), 'expected-command:pins|capture|replay');
  const args = {};
  const allowed = new Set(['pixi-package', 'playwright-package', 'chromium', 'chromium-root', 'workspace', 'runtime-lock']);
  while (argv.length) {
    const key = argv.shift();
    requireValue(key.startsWith('--') && allowed.has(key.slice(2)) && argv.length > 0 && !args[key.slice(2)], 'unsupported-or-duplicate-argument');
    args[key.slice(2)] = resolve(argv.shift());
  }
  for (const key of ['pixi-package', 'playwright-package', 'chromium', 'chromium-root']) requireValue(args[key], `missing-argument:${key}`);
  if (command !== 'pins') for (const key of ['workspace', 'runtime-lock']) requireValue(args[key], `missing-argument:${key}`);
  return { command, args };
}

async function main() {
  let browserResult;
  try {
    const { command, args } = parseArgs(process.argv.slice(2));
    const facts = await runtimeFacts(args);
    if (command === 'pins') {
      process.stdout.write(canonical(facts) + '\n');
      return;
    }
    const workspace = await realpath(args.workspace);
    requireValue(!under(workspace, await realpath(args['runtime-lock'])), 'runtime-lock-must-be-independently-held-outside-workspace');
    const lockBytes = await readFile(args['runtime-lock']);
    const lock = JSON.parse(lockBytes);
    requireValue(canonical(facts) === canonical(lock), 'runtime-pin-mismatch');
    const state = await boundWorkspace(workspace, command);
    browserResult = await replayScene(state, facts);
    const after = await boundWorkspace(workspace, command);
    requireValue(canonical(state.snapshotBinding) === canonical(after.snapshotBinding) && canonical(state.sources) === canonical(after.sources) && canonical(state.assets) === canonical(after.assets) && canonical(state.saved) === canonical(after.saved), 'inputs-changed-during-replay');
    requireValue(canonical(await runtimeFacts(args)) === canonical(facts), 'runtime-changed-during-replay');
    process.stdout.write(canonical({
      kind: 'img2.pixi2d-live-replay', version: 1, objectId: state.snapshot.objectId,
      nativeNodeProvenance: 'unevaluated', terminalAcceptance: false,
      snapshotSha256: state.snapshotSha256, snapshotBinding: state.snapshotBinding,
      captureBinding: state.saved.captureBinding, artifactBinding: state.saved.artifactBinding,
      replayCapture: browserResult.replayCapture, replayCaptureSha256: sha(canonical(browserResult.replayCapture)),
      matchesSavedCapture: command === 'replay' ? canonical(browserResult.replayCapture) === canonical(state.saved.capture) : null,
      sourceBindings: state.sources, assetBindings: state.assets,
      runtimeLockSha256: sha(lockBytes), runtime: facts,
      browserCommandLine: browserResult.browserCommandLine,
      browserVersion: browserResult.browserVersion, renderedHostSha256: browserResult.renderedHostSha256,
      approvedRuntimeRequests: browserResult.approvedRuntimeRequests,
      loadedResources: browserResult.loadedResources,
      limitations: ['Arbitrary entry/behavior JavaScript shares the mutable Pixi/browser realm; native-node-to-pixel provenance is unevaluated.', 'External CDP pixels and byte pins are replay evidence, not visual acceptance or terminal authorization.'],
    }) + '\n');
  } catch (error) {
    process.stdout.write(canonical({ kind: 'img2.pixi2d-live-replay', version: 1, status: 'blocked', nativeNodeProvenance: 'unevaluated', terminalAcceptance: false, reasons: [error.message] }) + '\n');
    process.exitCode = 2;
  }
}

await main();
