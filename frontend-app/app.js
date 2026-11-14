(function () {
  'use strict';
  const W = window.ZoairkWorld;
  const $ = id => document.getElementById(id);
  const world = W.createWorld();
  let revision = 0, socket = null, reconnectTimer = null, reconnectDelay = 3000, stopped = false;
  let pendingCommit = null, streamLine = null, route = '', lookRequested = false;
  const commandHistory = [];
  let historyIndex = 0, historyDraft = '';
  const defaultHost = location.hostname || 'localhost';
  $('ws-url').value = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${defaultHost}:8000/ws`;

  function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }
  function status(id, text, error = false) { $(id).textContent = text; $(id).classList.toggle('error', error); }
  function changed() {
    revision++;
    $('json-preview').textContent = JSON.stringify(world, null, 2);
    if (!pendingCommit) status('upload-status', 'Draft updated. Commit when you are ready.');
  }
  function field(entity, key, label, type = 'text', options) {
    const wrap = node('div');
    const elementId = entity.id + '-' + key;
    const caption = node('label', '', label);
    caption.htmlFor = elementId;
    const input = node(type === 'textarea' ? 'textarea' : type === 'select' ? 'select' : 'input');
    if (input.tagName === 'INPUT') input.type = 'text';
    input.id = elementId;
    input.dataset.entityId = entity.id;
    input.dataset.field = key;
    if (options) for (const value of options) input.add(new Option(value === 'unspecified' ? 'Unspecified' : value[0].toUpperCase() + value.slice(1), value));
    input.value = entity[key];
    wrap.append(caption, input);
    return wrap;
  }
  function action(label, name, ownerType, ownerId) {
    const button = node('button', 'secondary', label);
    button.type = 'button';
    Object.assign(button.dataset, { action: name, ownerType, ownerId });
    return button;
  }
  function stats() {
    const row = node('div', 'stats-placeholder');
    const placeholder = node('button', '', 'Add stats');
    placeholder.type = 'button';
    placeholder.disabled = true;
    placeholder.title = 'Reserved for the future stats editor';
    row.append(placeholder, node('span', '', 'Reserved for later'));
    return row;
  }
  function card(entity, kind, removable = true) {
    const outer = node('details', 'entity-card');
    outer.id = 'card-' + entity.id;
    outer.dataset.entityId = entity.id;
    outer.dataset.kind = kind;
    outer.open = true;
    const summary = node('summary');
    const heading = node('span');
    heading.append(node('span', 'entity-kind', kind));
    const title = node('span', 'entity-title', entity.name || 'Untitled');
    title.id = 'title-' + entity.id;
    heading.append(title);
    summary.append(heading);
    const body = node('div', 'entity-body');
    outer.append(summary, body);
    if (removable) {
      const remove = action('Remove ' + kind.toLowerCase(), 'remove', '', entity.id);
      remove.className = 'remove-button';
      // Appended after fields by finishCard, so remove never interrupts authoring.
      outer.removeControl = remove;
    }
    return { outer, body };
  }
  function finishCard(view) { if (view.outer.removeControl) view.body.append(view.outer.removeControl); return view.outer; }
  function objectsList(parent, ownerType) {
    const list = node('div', 'entity-list');
    list.id = 'objects-' + parent.id;
    for (const object of parent.objects) list.append(renderObject(object));
    return list;
  }
  function renderObject(object) {
    const view = card(object, 'Object');
    const parent = W.find(world, object.owner.id);
    view.body.append(node('p', 'owner-note', 'Belongs to ' + object.owner.type + ': ' + (parent.name || 'Untitled')),
      field(object, 'name', 'Object name'), field(object, 'description', 'Object description', 'textarea'),
      field(object, 'state', 'Object state', 'select', W.OBJECT_STATES), stats());
    return finishCard(view);
  }
  function renderNPC(npc) {
    const view = card(npc, 'NPC');
    view.body.append(field(npc, 'name', 'NPC name'), field(npc, 'description', 'NPC description', 'textarea'), stats(), objectsList(npc, 'npc'));
    const actions = node('div', 'entity-actions');
    actions.append(action('+ Add object', 'add-object', 'npc', npc.id));
    view.body.append(actions);
    return finishCard(view);
  }
  function updateDestinations() {
    for (const select of document.querySelectorAll('select[data-field="destinationSceneId"]')) {
      const exit = W.find(world, select.dataset.entityId, 'exit');
      select.replaceChildren(new Option('Choose a destination scene', ''));
      for (const scene of world.areas[0].scenes) select.add(new Option(scene.name || 'Untitled scene', scene.id));
      if (exit.destinationSceneId && !world.areas[0].scenes.some(scene => scene.id === exit.destinationSceneId)) {
        const missing = new Option('Removed scene — choose another destination', exit.destinationSceneId);
        missing.disabled = true;
        select.add(missing);
      }
      select.value = exit.destinationSceneId;
    }
  }
  function renderExit(exit) {
    const view = card(exit, 'Exit');
    view.body.append(field(exit, 'name', 'Exit name or direction'), field(exit, 'destinationSceneId', 'Destination scene', 'select', []));
    return finishCard(view);
  }
  function renderScene(scene) {
    const view = card(scene, 'Scene');
    view.body.append(field(scene, 'name', 'Scene name'), field(scene, 'description', 'Scene description', 'textarea'), objectsList(scene, 'scene'));
    const npcs = node('div', 'entity-list');
    npcs.id = 'npcs-' + scene.id;
    for (const npc of scene.npcs) npcs.append(renderNPC(npc));
    const exits = node('div', 'entity-list');
    exits.id = 'exits-' + scene.id;
    for (const exit of scene.exits) exits.append(renderExit(exit));
    const actions = node('div', 'entity-actions');
    actions.append(action('+ Add object', 'add-object', 'scene', scene.id), action('+ Add NPC', 'add-npc', 'scene', scene.id), action('+ Add exit', 'add-exit', 'scene', scene.id));
    view.body.append(npcs, exits, actions);
    return finishCard(view);
  }
  function renderPlayer() {
    $('player-editor').replaceChildren();
    $('create-player').hidden = !!world.player;
    if (!world.player) return;
    const player = world.player;
    const view = card(player, 'Player');
    view.body.append(field(player, 'name', 'Character name'), stats(), objectsList(player, 'player'));
    const actions = node('div', 'entity-actions');
    actions.append(action('+ Add item', 'add-object', 'player', player.id));
    const backstoryButton = action('+ Add backstory', 'backstory', 'player', player.id);
    actions.append(backstoryButton);
    const backstory = field(player, 'backstory', 'Backstory', 'textarea');
    backstory.id = 'player-backstory';
    backstory.hidden = !player.backstory;
    backstoryButton.hidden = !!player.backstory;
    view.body.append(actions, backstory);
    $('player-editor').append(finishCard(view));
  }
  function renderEntities() {
    const closed = new Set([...document.querySelectorAll('.entity-card:not([open])')].map(element => element.id));
    $('scenes').replaceChildren(...world.areas[0].scenes.map(renderScene));
    renderPlayer();
    for (const entityId of closed) if ($(entityId)) $(entityId).open = false;
    updateDestinations();
  }
  $('area-name').addEventListener('input', event => { world.areas[0].name = event.target.value; changed(); });
  $('area-description').addEventListener('input', event => { world.areas[0].description = event.target.value; changed(); });
  $('world-form').addEventListener('input', event => {
    const { entityId, field: key } = event.target.dataset;
    if (!entityId || !key) return;
    const entity = W.find(world, entityId);
    entity[key] = event.target.value;
    if (key === 'name') {
      $('title-' + entityId).textContent = entity.name || 'Untitled';
      // Owner labels are display-only; the immutable owner ID is the actual relationship.
      for (const object of entity.objects || []) {
        const note = $('card-' + object.id)?.querySelector('.owner-note');
        if (note) note.textContent = 'Belongs to ' + object.owner.type + ': ' + (entity.name || 'Untitled');
      }
      updateDestinations();
    }
    changed();
  });
  $('add-scene').addEventListener('click', () => {
    const scene = W.addScene(world);
    $('scenes').append(renderScene(scene));
    updateDestinations();
    changed();
    $(scene.id + '-name').focus();
  });
  $('create-player').addEventListener('click', () => { const player = W.addPlayer(world); renderPlayer(); changed(); $(player.id + '-name').focus(); });
  $('world-form').addEventListener('click', event => {
    const button = event.target.closest('button[data-action]');
    if (!button) return;
    const { action: name, ownerType, ownerId } = button.dataset;
    if (name === 'add-object') {
      const object = W.addObject(world, ownerType, ownerId);
      $('objects-' + ownerId).append(renderObject(object));
      $(object.id + '-name').focus();
    } else if (name === 'add-npc') {
      const npc = W.addNPC(world, ownerId);
      $('npcs-' + ownerId).append(renderNPC(npc));
      $(npc.id + '-name').focus();
    } else if (name === 'add-exit') {
      const exit = W.addExit(world, ownerId);
      $('exits-' + ownerId).append(renderExit(exit));
      updateDestinations();
      $(exit.id + '-name').focus();
    } else if (name === 'backstory') {
      $('player-backstory').hidden = false;
      button.hidden = true;
      $(world.player.id + '-backstory').focus();
    } else if (name === 'remove') { W.remove(world, ownerId); renderEntities(); }
    changed();
  });

  function connectionState(connected, text) {
    $('ws-status').textContent = text;
    $('connection-dot').classList.toggle('connected', connected);
  }
  function appendLine(text, type = 'engine') {
    const line = node('p', 'msg ' + type, String(text));
    $('terminal-output').append(line);
    $('terminal-output').scrollTop = $('terminal-output').scrollHeight;
    return line;
  }
  function send(type, payload) {
    if (!socket || socket.readyState !== WebSocket.OPEN) return false;
    const encoded = W.message(type, payload);
    if (!encoded) return false;
    try { socket.send(encoded); return true; } catch { return false; }
  }
  function finishCommit(text, error = false) {
    if (pendingCommit) clearTimeout(pendingCommit.timer);
    pendingCommit = null;
    $('commit-world').disabled = false;
    $('commit-world').textContent = 'Commit world';
    status('upload-status', text, error);
  }
  function startPlay() {
    if (route !== 'play' || lookRequested) return;
    if (send('command', { command: 'look' })) { lookRequested = true; status('play-status', 'Connected. Waiting for the engine…'); }
  }
  function handleMessage(raw) {
    let message;
    try { message = JSON.parse(raw); }
    catch { streamLine = null; appendLine(raw); status('play-status', 'Connected'); return; }
    if (!message || typeof message !== 'object') { appendLine(String(message)); return; }
    if (message.type === 'game_created') {
      if (pendingCommit) finishCommit(pendingCommit.revision === revision ? (message.message || 'World committed. Open Play a game to begin.') : 'The earlier draft was committed. Commit again to send your newer edits.');
      return;
    }
    if (message.type === 'error') {
      const text = typeof message.message === 'string' ? message.message : 'The engine reported an error.';
      if (pendingCommit) finishCommit(text, true);
      status('play-status', text, true);
      appendLine(text, 'system');
      streamLine = null;
      return;
    }
    if (message.type === 'done' || message.type === 'stream_end') { streamLine = null; status('play-status', 'Connected'); return; }
    const text = typeof message.text === 'string' ? message.text : typeof message.delta === 'string' ? message.delta : typeof message.output === 'string' ? message.output : null;
    if (text === null) { status('play-status', 'Received an unsupported backend message.', true); return; }
    const isChunk = ['chunk', 'delta', 'stream_chunk'].includes(message.type) || message.stream === true;
    if (isChunk) {
      if (!streamLine) streamLine = appendLine('');
      streamLine.append(document.createTextNode(text));
      $('terminal-output').scrollTop = $('terminal-output').scrollHeight;
      if (message.done) streamLine = null;
    } else { streamLine = null; appendLine(text); }
    status('play-status', isChunk && !message.done ? 'Receiving output…' : 'Connected');
  }
  function connect() {
    let url;
    try { url = W.websocketURL($('ws-url').value.trim()); }
    catch (error) { status('connection-message', error.message, true); return; }
    if (location.protocol === 'https:' && url.startsWith('ws:')) { status('connection-message', 'This HTTPS page needs a wss:// backend URL.', true); return; }
    clearTimeout(reconnectTimer);
    // A new connection needs its own initial scene, even when Play stays open.
    lookRequested = false;
    streamLine = null;
    if (pendingCommit) finishCommit('Connection changed before confirmation. Check the backend before committing again.', true);
    if (socket) { const old = socket; socket = null; old.close(); }
    connectionState(false, 'Connecting to backend…');
    let current;
    try { current = new WebSocket(url); } catch (error) { connectionState(false, 'Backend disconnected'); status('connection-message', error.message, true); return; }
    socket = current;
    current.addEventListener('open', () => {
      if (socket !== current) return;
      reconnectDelay = 3000;
      connectionState(true, 'Backend connected');
      status('connection-message', 'Connected to ' + url);
      status('play-status', 'Connected');
      startPlay();
    });
    current.addEventListener('message', event => { if (socket === current && typeof event.data === 'string') handleMessage(event.data); });
    current.addEventListener('error', () => { if (socket === current) current.close(); });
    current.addEventListener('close', () => {
      if (socket !== current || stopped) return;
      connectionState(false, 'Backend disconnected');
      status('connection-message', 'Backend unavailable. Check the URL and start your engine; retrying automatically.');
      status('play-status', 'Disconnected. Your command has not been resent.', true);
      if (pendingCommit) finishCommit('Connection lost before confirmation. Check the backend before committing again.', true);
      streamLine = null;
      lookRequested = false;
      reconnectTimer = setTimeout(connect, reconnectDelay);
      reconnectDelay = Math.min(reconnectDelay * 2, 30000);
    });
  }
  $('connection-form').addEventListener('submit', event => { event.preventDefault(); reconnectDelay = 3000; connect(); });
  $('world-form').addEventListener('submit', event => {
    event.preventDefault();
    if (pendingCommit) return;
    let compiled;
    try { compiled = W.compile(world); }
    catch (error) { status('upload-status', error.message, true); return; }
    if (!send('create_game', compiled)) { status('upload-status', 'Cannot commit: connect to the backend first. Your draft is still here.', true); return; }
    pendingCommit = { revision, timer: setTimeout(() => finishCommit('No confirmation received. Check the backend before retrying the commit.', true), 20000) };
    $('commit-world').disabled = true;
    $('commit-world').textContent = 'Committing…';
    status('upload-status', 'World sent. Waiting for backend confirmation…');
  });
  $('terminal-form').addEventListener('submit', event => {
    event.preventDefault();
    const command = $('command-input').value.trim();
    if (!command) return;
    if (!send('command', { command })) { status('play-status', 'Cannot send: the backend is disconnected. Your command has been kept.', true); return; }
    streamLine = null;
    appendLine('> ' + command, 'user');
    commandHistory.push(command);
    historyIndex = commandHistory.length;
    historyDraft = '';
    $('command-input').value = '';
    status('play-status', 'Waiting for the engine…');
  });
  $('command-input').addEventListener('keydown', event => {
    if (event.key === 'ArrowUp' && historyIndex > 0) {
      event.preventDefault();
      if (historyIndex === commandHistory.length) historyDraft = event.target.value;
      event.target.value = commandHistory[--historyIndex];
    } else if (event.key === 'ArrowDown' && historyIndex < commandHistory.length) {
      event.preventDefault();
      event.target.value = ++historyIndex === commandHistory.length ? historyDraft : commandHistory[historyIndex];
    }
  });
  function navigate() {
    const next = location.hash.replace(/^#\/?/, '') || 'home';
    const current = ['create', 'play'].includes(next) ? next : 'home';
    if (route !== current) lookRequested = false;
    route = current;
    for (const name of ['home', 'create', 'play']) $('view-' + name).hidden = name !== route;
    if (route === 'play') { $('command-input').focus(); startPlay(); }
    window.scrollTo(0, 0);
  }
  window.addEventListener('hashchange', navigate);
  window.addEventListener('pagehide', () => { stopped = true; clearTimeout(reconnectTimer); if (pendingCommit) clearTimeout(pendingCommit.timer); if (socket) socket.close(); });
  $('json-preview').textContent = JSON.stringify(world, null, 2);
  navigate();
  connect();
})();
