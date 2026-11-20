// Real PixiJS replay regression scene, NOT a user's reconstruction or fidelity proof.
import { createBadge } from './shape.mjs';

export function createRoutedPixiScene({ app, PIXI, assets }) {
  if (Object.keys(assets).length !== 0) throw new Error('fixture-expects-no-loaded-assets');
  const nodes = new Map();
  const sharedConsumer = new PIXI.Sprite(PIXI.Texture.WHITE);
  sharedConsumer.visible = false;
  app.stage.addChild(sharedConsumer);
  let root;
  const construct = () => {
    root = new PIXI.Container({ label: 'real-replay-fixture' });
    const badge = createBadge(PIXI);
    const marker = new PIXI.Graphics().circle(0, 0, 6).fill(0xe84a5f);
    marker.position.set(40, 40);
    root.addChild(badge, marker);
    nodes.set('badge', badge);
    nodes.set('marker', marker);
    return root;
  };
  const handle = {
    root: construct(), nodes,
    behaviors: {
      'motion-end': {
        run() { nodes.get('badge').position.set(24, 8); },
        reset() { nodes.get('badge').position.set(8, 8); },
      },
      lifecycle: {
        run() {
          root.removeFromParent();
          root.destroy({ children: true, texture: false, textureSource: false });
          if (sharedConsumer.texture.source.destroyed) throw new Error('shared-resource-was-destroyed');
          handle.root = construct();
          app.stage.addChild(handle.root);
        },
        reset() { nodes.get('badge').position.set(8, 8); },
      },
    },
    dispose() {
      root.removeFromParent();
      root.destroy({ children: true, texture: false, textureSource: false });
      sharedConsumer.removeFromParent();
      sharedConsumer.destroy({ texture: false, textureSource: false });
    },
  };
  return handle;
}
