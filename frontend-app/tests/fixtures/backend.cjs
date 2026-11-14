// Test-only protocol peer. This is not the game engine and never runs with npm start.
const { WebSocketServer } = require('ws');
const W = require('../../world.js');
async function createBackend(port = 0) {
  const server = new WebSocketServer({ port, host: '127.0.0.1', path: '/ws' });
  await new Promise((resolve, reject) => { server.once('listening', resolve); server.once('error', reject); });
  const messages = [];
  server.on('connection', socket => {
    let world = null;
    socket.on('message', raw => {
      let message;
      try { message = JSON.parse(raw); } catch { socket.send(JSON.stringify({ type: 'error', message: 'Protocol fixture: invalid JSON' })); return; }
      messages.push(message);
      if (message.type === 'create_game') {
        try { W.compile(message.payload); } catch (error) { socket.send(JSON.stringify({ type: 'error', message: error.message })); return; }
        world = message.payload;
        setTimeout(() => { if (socket.readyState === 1) socket.send(JSON.stringify({ type: 'game_created', message: 'Protocol test: world JSON received and validated.' })); }, 200);
      } else if (message.type === 'command') {
        const command = message.payload.command;
        if (command === 'fixture:error') { socket.send(JSON.stringify({ type: 'error', message: 'Protocol test: command rejected' })); return; }
        if (command === 'fixture:disconnect') { socket.close(); return; }
        if (command === 'fixture:malformed') { socket.send(JSON.stringify({ type: 'output', text: {} })); return; }
        if (command === 'look') socket.send(JSON.stringify({ type: 'output', text: 'Protocol test output. ' + (world ? world.areas[0].scenes[0].name : 'No game engine is running in this fixture.') }));
        else {
          socket.send(JSON.stringify({ type: 'chunk', text: 'Protocol test: ' }));
          socket.send(JSON.stringify({ type: 'chunk', text: command }));
          socket.send(JSON.stringify({ type: 'done' }));
        }
      }
    });
  });
  return { server, messages, port: server.address().port, close: async () => { for (const socket of server.clients) socket.terminate(); await new Promise(resolve => server.close(resolve)); } };
}
module.exports = { createBackend };
if (require.main === module) createBackend(Number(process.env.FIXTURE_PORT || 8082)).then(peer => console.log('TEST ONLY WebSocket protocol peer: ws://127.0.0.1:' + peer.port + '/ws'));
