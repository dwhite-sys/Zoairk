const { test } = require('node:test');
const assert = require('node:assert/strict');
const { once } = require('node:events');
const { WebSocket } = require('ws');
const { createBackend } = require('./fixtures/backend.cjs');
const { createServer } = require('../scripts/serve.cjs');
const W = require('../world.js');
test('static server serves the three screens and only frontend assets', async () => {
  const server = createServer(); await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const base = 'http://127.0.0.1:' + server.address().port;
    const html = await (await fetch(base)).text();
    for (const name of ['view-home', 'view-create', 'view-play']) assert.ok(html.includes(name));
    for (const file of ['style.css', 'app.js', 'world.js']) assert.equal((await fetch(base + '/' + file)).status, 200);
    assert.equal((await fetch(base + '/.git/config')).status, 404);
  } finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
});
test('real WebSocket transport receives hierarchical JSON, acknowledges it, and streams command output', async () => {
  const peer = await createBackend();
  const socket = new WebSocket('ws://127.0.0.1:' + peer.port + '/ws');
  try {
    await once(socket, 'open');
    const world = W.createWorld(); world.areas[0].name = 'Coast'; W.addScene(world).name = 'Harbor'; W.addPlayer(world).name = 'Mira';
    const npc = W.addNPC(world, world.areas[0].scenes[0].id); npc.name = 'Guard'; W.addObject(world, 'npc', npc.id).name = 'Key';
    const ack = once(socket, 'message'); socket.send(W.message('create_game', W.compile(world)));
    assert.equal(JSON.parse((await ack)[0]).type, 'game_created');
    const output = [];
    const done = new Promise(resolve => socket.on('message', raw => { const message = JSON.parse(raw); output.push(message); if (message.type === 'done') resolve(); }));
    socket.send(W.message('command', { command: 'open door' })); await done;
    assert.equal(output.filter(m => m.type === 'chunk').map(m => m.text).join(''), 'Protocol test: open door');
    assert.equal(peer.messages[0].payload.areas[0].scenes[0].npcs[0].objects[0].owner.id, npc.id);
  } finally { socket.terminate(); await peer.close(); }
});
