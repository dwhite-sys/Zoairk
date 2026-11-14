(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.ZoairkWorld = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  // Provisional authoring states; replace this list when the engine defines its vocabulary.
  const OBJECT_STATES = ['unspecified', 'open', 'closed', 'locked', 'unlocked', 'on', 'off', 'intact', 'broken'];
  let counter = 0;
  const id = type => type + '_' + Date.now().toString(36) + '_' + (++counter).toString(36) + '_' + Math.random().toString(36).slice(2, 8);
  function createWorld() { return { schemaVersion: 1, areas: [{ id: id('area'), name: '', description: '', scenes: [] }], player: null }; }
  function entities(world) {
    const result = [];
    function add(entity, type) { result.push({ entity, type }); }
    for (const area of world.areas) {
      add(area, 'area');
      for (const scene of area.scenes) {
        add(scene, 'scene');
        for (const object of scene.objects) add(object, 'object');
        for (const npc of scene.npcs) { add(npc, 'npc'); for (const object of npc.objects) add(object, 'object'); }
        for (const exit of scene.exits) add(exit, 'exit');
      }
    }
    if (world.player) { add(world.player, 'player'); for (const object of world.player.objects) add(object, 'object'); }
    return result;
  }
  function find(world, entityId, expected) {
    const found = entities(world).find(item => item.entity.id === entityId);
    if (!found || expected && found.type !== expected) throw new Error('The selected ' + (expected || 'entity') + ' no longer exists.');
    return found.entity;
  }
  function addScene(world) {
    const scene = { id: id('scene'), name: '', description: '', objects: [], npcs: [], exits: [] };
    world.areas[0].scenes.push(scene);
    return scene;
  }
  function addNPC(world, sceneId) {
    const scene = find(world, sceneId, 'scene');
    const npc = { id: id('npc'), name: '', description: '', stats: null, objects: [] };
    scene.npcs.push(npc);
    return npc;
  }
  function addPlayer(world) {
    if (world.player) return world.player;
    world.player = { id: id('player'), name: '', stats: null, objects: [], backstory: '' };
    return world.player;
  }
  function addObject(world, ownerType, ownerId) {
    if (!['scene', 'npc', 'player'].includes(ownerType)) throw new Error('Objects must belong to a scene, NPC, or player.');
    const parent = find(world, ownerId, ownerType);
    const object = { id: id('object'), name: '', description: '', state: 'unspecified', stats: null, owner: { type: ownerType, id: ownerId } };
    parent.objects.push(object);
    return object;
  }
  function addExit(world, sceneId) {
    const scene = find(world, sceneId, 'scene');
    const exit = { id: id('exit'), name: '', destinationSceneId: '' };
    scene.exits.push(exit);
    return exit;
  }
  function remove(world, entityId) {
    for (const area of world.areas) {
      for (const scene of area.scenes) {
        for (const collection of [scene.objects, scene.exits, scene.npcs, ...scene.npcs.map(npc => npc.objects)]) {
          const index = collection.findIndex(entity => entity.id === entityId);
          if (index >= 0) { collection.splice(index, 1); return; }
        }
      }
      const index = area.scenes.findIndex(scene => scene.id === entityId);
      if (index >= 0) { area.scenes.splice(index, 1); return; }
    }
    if (world.player) {
      const index = world.player.objects.findIndex(object => object.id === entityId);
      if (index >= 0) { world.player.objects.splice(index, 1); return; }
      if (world.player.id === entityId) { world.player = null; return; }
    }
    throw new Error('Nothing to remove.');
  }
  function validate(world) {
    const errors = [];
    const scenes = world.areas.flatMap(area => area.scenes);
    const sceneIds = new Set(scenes.map(scene => scene.id));
    const all = entities(world);
    if (new Set(all.map(item => item.entity.id)).size !== all.length) errors.push('Every entity must have a unique ID.');
    if (!world.areas[0]?.name.trim()) errors.push('Give the area a name.');
    if (!scenes.length) errors.push('Add at least one scene.');
    for (const scene of scenes) {
      if (!scene.name.trim()) errors.push('Give each scene a name.');
      const exitNames = new Set();
      for (const exit of scene.exits) {
        if (!exit.name.trim()) errors.push('Give every exit a name or direction.');
        if (exitNames.has(exit.name.trim().toLowerCase())) errors.push('Exit names must be unique within a scene.');
        exitNames.add(exit.name.trim().toLowerCase());
        if (!sceneIds.has(exit.destinationSceneId)) errors.push('Choose an existing destination scene for every exit.');
      }
      for (const npc of scene.npcs) {
        if (!npc.name.trim()) errors.push('Give each NPC a name.');
        checkObjects(npc.objects, 'npc', npc.id);
      }
      checkObjects(scene.objects, 'scene', scene.id);
    }
    if (!world.player?.name.trim()) errors.push('Create a player and give the character a name.');
    if (world.player) checkObjects(world.player.objects, 'player', world.player.id);
    function checkObjects(objects, type, ownerId) {
      for (const object of objects) {
        if (!object.name.trim()) errors.push('Give each object a name.');
        if (object.owner?.type !== type || object.owner?.id !== ownerId) errors.push('An object has an invalid owner.');
        if (!OBJECT_STATES.includes(object.state)) errors.push('Choose an available object state.');
      }
    }
    return [...new Set(errors)];
  }
  function compile(world) {
    const errors = validate(world);
    if (errors.length) throw new Error(errors.join(' '));
    const result = structuredClone(world);
    result.player.startingSceneId = result.areas[0].scenes[0].id;
    return result;
  }
  function message(type, payload) {
    if (!['create_game', 'command'].includes(type)) throw new Error('Unsupported outgoing message type.');
    if (type === 'command' && (typeof payload?.command !== 'string' || !payload.command.trim())) return null;
    return JSON.stringify({ type, payload });
  }
  function websocketURL(value) {
    let url;
    try { url = new URL(value); } catch { throw new Error('Enter a complete ws:// or wss:// backend URL.'); }
    if (!['ws:', 'wss:'].includes(url.protocol) || url.username || url.password) throw new Error('Use a ws:// or wss:// backend URL without embedded credentials.');
    return url.href;
  }
  return { OBJECT_STATES, createWorld, entities, find, addScene, addNPC, addPlayer, addObject, addExit, remove, validate, compile, message, websocketURL };
});
