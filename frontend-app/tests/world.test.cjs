const { test } = require('node:test');
const assert = require('node:assert/strict');
const W = require('../world.js');
function validWorld() {
  const world = W.createWorld();
  world.areas[0].name = 'The Coast';
  W.addScene(world).name = 'Harbor';
  W.addPlayer(world).name = 'Mira';
  return world;
}
test('objects keep their exact scene, NPC, or player owner even with duplicate names', () => {
  const world = validWorld();
  const [scene] = world.areas[0].scenes;
  const npc = W.addNPC(world, scene.id); npc.name = 'Guard';
  const second = W.addScene(world); second.name = 'Harbor';
  for (const [type, owner] of [['scene', scene], ['scene', second], ['npc', npc], ['player', world.player]]) {
    const object = W.addObject(world, type, owner.id); object.name = 'Key';
    assert.deepEqual(object.owner, { type, id: owner.id });
    assert.equal(owner.objects[0], object);
  }
  assert.deepEqual(W.validate(world), []);
  assert.throws(() => W.addObject(world, 'area', world.areas[0].id));
  assert.throws(() => W.addObject(world, 'npc', scene.id));
});
test('compiling preserves hierarchy, stats placeholders, backstory, and starting scene', () => {
  const world = validWorld(); world.player.backstory = 'A traveler from the north.';
  const object = W.addObject(world, 'player', world.player.id); object.name = 'Map';
  const compiled = W.compile(world);
  assert.equal(compiled.player.startingSceneId, compiled.areas[0].scenes[0].id);
  assert.equal(compiled.player.backstory, world.player.backstory);
  assert.equal(compiled.player.stats, null);
  assert.equal(compiled.player.objects[0].stats, null);
  compiled.player.name = 'Changed';
  assert.equal(world.player.name, 'Mira');
});
test('empty world and wrong input cannot be committed', () => {
  assert.throws(() => W.compile(W.createWorld()), /area a name/);
  const world = validWorld();
  const object = W.addObject(world, 'player', world.player.id);
  assert.throws(() => W.compile(world), /object a name/);
  object.name = 'Key'; object.owner.id = 'nonexistent';
  assert.throws(() => W.compile(world), /invalid owner/);
  object.owner.id = world.player.id; object.state = 'unknown';
  assert.throws(() => W.compile(world), /object state/);
});
test('exits require a destination and removed scenes never silently retarget them', () => {
  const world = validWorld(); const start = world.areas[0].scenes[0];
  const destination = W.addScene(world); destination.name = 'Forest';
  const exit = W.addExit(world, start.id); exit.name = 'north';
  assert.throws(() => W.compile(world), /destination/);
  exit.destinationSceneId = destination.id;
  assert.doesNotThrow(() => W.compile(world));
  W.remove(world, destination.id);
  assert.throws(() => W.compile(world), /destination/);
});
test('adding player twice is idempotent; entity IDs remain unique', () => {
  const world = validWorld();
  const player = W.addPlayer(world);
  assert.equal(W.addPlayer(world), player);
  for (let i = 0; i < 100; i++) W.addObject(world, 'player', player.id).name = 'Item';
  const ids = W.entities(world).map(item => item.entity.id);
  assert.equal(new Set(ids).size, ids.length);
});
test('removing NPCs and scenes also removes their owned items', () => {
  const world = validWorld(); const scene = world.areas[0].scenes[0];
  const npc = W.addNPC(world, scene.id); const object = W.addObject(world, 'npc', npc.id);
  W.remove(world, npc.id);
  assert.throws(() => W.find(world, object.id));
  const loose = W.addObject(world, 'scene', scene.id);
  W.remove(world, scene.id);
  assert.throws(() => W.find(world, loose.id));
});
test('protocol retains the boilerplate envelope; blank commands produce no message', () => {
  assert.equal(W.message('command', { command: '  ' }), null);
  assert.deepEqual(JSON.parse(W.message('command', { command: 'look' })), { type: 'command', payload: { command: 'look' } });
  assert.throws(() => W.message('unknown', {}));
});
test('endpoint validation accepts ws/wss and rejects malformed or credential URLs', () => {
  assert.equal(W.websocketURL('ws://localhost:8000/ws'), 'ws://localhost:8000/ws');
  assert.equal(W.websocketURL('wss://example.com/ws'), 'wss://example.com/ws');
  for (const url of ['', 'gibberish', 'https://example.com', 'ws://user:secret@example.com/ws']) assert.throws(() => W.websocketURL(url));
});
module.exports = { validWorld };
