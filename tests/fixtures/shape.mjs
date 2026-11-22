// Real native geometry used by the routed-scene fixture's executable dependency.
export function createBadge(PIXI) {
  const node = new PIXI.Graphics().rect(0, 0, 16, 16).fill(0x36c57a);
  node.position.set(8, 8);
  return node;
}
