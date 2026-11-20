/** CONFIG is injected by the pinned driver; this host exports no source-authentication authority. */
import * as PIXI from '/runtime/pixi.mjs';
import { captureEditableScene } from '/runtime/review-capture.mjs';

const externalFrame = globalThis.__pixiReplayFrame;
const replaceChildren = Function.prototype.call.bind(Element.prototype.replaceChildren);
const remove = Function.prototype.call.bind(Element.prototype.remove);
const setAttribute = Function.prototype.call.bind(Element.prototype.setAttribute);
const querySelectorAll = Function.prototype.call.bind(Document.prototype.querySelectorAll);
const finish = value => Object.defineProperty(globalThis, '__pixiReplayFinished', { value, configurable: false, writable: false });

let app;
let handle;
let initialized = false;
let outcome;
try {
  if (PIXI.VERSION !== '8.22.0') throw new Error('pinned-pixi-version-mismatch');
  // Official pinned Pixi CSP compatibility: static uniform/shader sync functions,
  // not a relaxation of script-src or permission to evaluate generated source.
  globalThis.PIXI = { ...PIXI };
  await new Promise((accept, reject) => {
    const compatibility = document.createElement('script');
    compatibility.src = '/runtime/unsafe-eval.js';
    compatibility.onload = accept;
    compatibility.onerror = () => reject(new Error('pinned-pixi-csp-module-load-failed'));
    document.head.appendChild(compatibility);
  });
  const profile = CONFIG.profile;
  app = new PIXI.Application();
  await app.init({ width: profile.width, height: profile.height, resolution: 1, antialias: profile.antialias, background: profile.background, backgroundAlpha: profile.backgroundAlpha, preference: 'webgl', autoStart: false, sharedTicker: false, preserveDrawingBuffer: true });
  initialized = true;
  const canvas = app.canvas;
  const assets = Object.create(null);
  for (const asset of CONFIG.assets) {
    const url = '/workspace/' + asset.path;
    if (asset.type === 'texture') assets[asset.alias] = await PIXI.Assets.load(url);
    else if (asset.type === 'font') {
      const font = new FontFace(asset.alias, `url(${JSON.stringify(url)})`);
      await font.load();
      document.fonts.add(font);
      assets[asset.alias] = font;
    } else {
      const response = await fetch(url);
      if (!response.ok) throw new Error(`asset-load-failed:${asset.path}`);
      assets[asset.alias] = asset.type === 'json' ? await response.json() : new Uint8Array(await response.arrayBuffer());
    }
  }
  await document.fonts.ready;
  const reportPolicyViolation = globalThis.__pixiReplayViolation;
  document.addEventListener('securitypolicyviolation', event => {
    void reportPolicyViolation(CONFIG.nonce, event.blockedURI, event.effectiveDirective);
  }, true);
  const entry = await import(CONFIG.entry);
  if (typeof entry.createRoutedPixiScene !== 'function') throw new Error('createRoutedPixiScene-export-required');
  handle = await entry.createRoutedPixiScene({ app, PIXI, assets });
  if (!(handle?.root instanceof PIXI.Container)) throw new Error('native-root-required');
  if (!handle.root.parent) app.stage.addChild(handle.root);
  if (handle.root.parent !== app.stage) throw new Error('routed-root-must-belong-to-fixed-host');
  app.stop();
  await captureEditableScene({
    app, handle, PIXI, snapshot: CONFIG.snapshot, behaviors: handle.behaviors,
    captureFrame: async key => {
      // Restore fixed viewport presentation, not a second rendering of the artwork.
      for (const element of querySelectorAll(document, 'style,link[rel="stylesheet"]')) remove(element);
      document.adoptedStyleSheets = [];
      replaceChildren(document.body, canvas);
      setAttribute(document.documentElement, 'style', 'margin:0;padding:0;width:100%;height:100%;overflow:hidden;background:transparent');
      setAttribute(document.body, 'style', 'margin:0;padding:0;width:100%;height:100%;overflow:hidden;background:transparent');
      setAttribute(canvas, 'style', 'display:block;position:absolute;left:0;top:0;margin:0;padding:0;border:0;transform:none;opacity:1;visibility:visible;filter:none;mix-blend-mode:normal');
      if (canvas.width !== profile.width || canvas.height !== profile.height) throw new Error('canvas-dimensions-changed');
      return await externalFrame(CONFIG.nonce, key);
    },
  });
  if (typeof handle.dispose === 'function') await handle.dispose();
  outcome = { ok: true };
} catch (error) {
  outcome = { ok: false, error: String(error?.message ?? error) };
} finally {
  // This realm runs arbitrary bound source; CDP evidence explicitly leaves native
  // graph provenance unevaluated even if all observed instance checks succeed.
  if (initialized) {
    try { app.destroy(true, { children: true, texture: false, textureSource: false }); }
    catch (error) { outcome = { ok: false, error: `${outcome?.error ?? 'replay-complete'}; cleanup:${String(error?.message ?? error)}` }; }
  }
}
finish(outcome);
