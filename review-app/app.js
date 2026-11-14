/* Review decisions are mirrored to the server so progress survives a browser and
   is shared across devices; imported example files themselves are never uploaded. */
(function () {
  'use strict';
  const R = window.ZoairkReview;
  const $ = id => document.getElementById(id);
  let entries = [], selected = 0, filter = 'pending', busy = true, database = null;
  let clientId = null, serverSaved = false, syncedFromServer = 0, loadedFromServer = 0;
  const history = [];
  function notice(message, error = false) {
    $('notice').textContent = message;
    $('notice').classList.toggle('error', error);
    $('notice').hidden = false;
  }
  function visibleIndices() { return entries.map((e, i) => i).filter(i => filter === 'all' || (filter === 'reviewed' ? !!entries[i].decision : !entries[i].decision)); }
  function render() {
    const count = R.counts(entries);
    $('total-count').textContent = count.total;
    $('approved-count').textContent = count.approved;
    $('denied-count').textContent = count.denied;
    $('pending-count').textContent = count.pending;
    $('pending-tab-count').textContent = count.pending;
    $('progress-bar').style.width = (count.total ? 100 * (count.approved + count.denied) / count.total : 0) + '%';
    $('progress-caption').textContent = count.total ? `${count.approved + count.denied} of ${count.total} reviewed` : 'Import a file to begin';
    $('empty-state').hidden = !!count.total;
    $('workspace').hidden = !count.total;
    $('export-needle').disabled = busy || !count.approved;
    $('export-classifier').disabled = busy || !(count.approved + count.denied);
    $('export-session').disabled = busy || !count.total;
    $('file-input').disabled = busy;
    $('load-sample').disabled = busy;
    $('undo').disabled = busy || !history.length;
    const indices = visibleIndices();
    if (!indices.includes(selected)) selected = indices.find(i => i >= selected) ?? indices[0] ?? 0;
    const position = indices.indexOf(selected);
    $('position').textContent = indices.length ? `${position + 1} / ${indices.length}` : '0 remaining';
    $('review-layout').hidden = !indices.length;
    $('queue-empty').hidden = !!indices.length;
    $('queue-empty-title').textContent = filter === 'reviewed' ? 'No reviews yet.' : 'You’re all caught up.';
    $('queue-empty-text').textContent = filter === 'reviewed' ? 'Choose Pending to start reviewing your examples.' : 'Export your datasets, or import another batch to keep going.';
    $('previous').disabled = busy || position <= 0;
    $('next').disabled = busy || position < 0 || position >= indices.length - 1;
    document.querySelectorAll('[data-filter]').forEach(button => {
      button.classList.toggle('active', button.dataset.filter === filter);
      button.setAttribute('aria-pressed', String(button.dataset.filter === filter));
      button.disabled = busy;
    });
    $('save-status').textContent = busy ? 'Saving…' : database ? (serverSaved ? 'Saved on the server' : 'Saved in this browser') : 'Temporary session — export before leaving';
    $('approve').disabled = busy;
    $('deny').disabled = busy;
    $('clear-decision').disabled = busy;
    $('review-reason').disabled = busy;
    if (!indices.length) return;
    const entry = entries[selected];
    $('query').textContent = entry.example.query;
    $('decision-badge').textContent = entry.decision === 'approve' ? 'Approved' : entry.decision === 'deny' ? 'Denied' : 'Pending review';
    $('decision-badge').className = 'badge' + (entry.decision === 'approve' ? ' approved' : entry.decision === 'deny' ? ' denied' : '');
    $('call-count').textContent = `${entry.example.answers.length} call${entry.example.answers.length === 1 ? '' : 's'}`;
    $('calls').replaceChildren();
    for (const call of entry.example.answers) {
      const item = document.createElement('li');
      const name = document.createElement('div');
      name.className = 'call-name';
      name.textContent = call.name;
      const args = document.createElement('pre');
      args.textContent = JSON.stringify(call.arguments, null, 2);
      item.append(name, args);
      $('calls').append(item);
    }
    if (!entry.example.answers.length) {
      const empty = document.createElement('p');
      empty.className = 'no-calls';
      empty.textContent = 'No tool calls proposed. Approve only if taking no action is correct for this input.';
      $('calls').append(empty);
    }
    $('reasoning').textContent = entry.example.reasoning || 'No reasoning provided.';
    $('tools').textContent = JSON.stringify(entry.example.tools, null, 2);
    $('review-reason').value = entry.reason;
    $('clear-decision').hidden = !entry.decision;
  }
  async function openStorage() {
    database = await new Promise((resolve, reject) => {
      const request = indexedDB.open('zoairk-example-review', 1);
      request.onupgradeneeded = () => request.result.createObjectStore('workspace');
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
      request.onblocked = () => reject(new Error('Close other Zoairk tabs and reload to enable saved progress.'));
    });
    database.onversionchange = () => { database.close(); database = null; notice('Local storage changed in another tab. Export this session before leaving.', true); render(); };
    const saved = await new Promise((resolve, reject) => {
      const request = database.transaction('workspace').objectStore('workspace').get('session');
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    if (saved) entries = R.parseFile(saved).entries;
    clientId = await loadClientId();
    await mergeServer();
    // Catch up work done while the server was unreachable. Only for a browser
    // with its own saved session, so a first-time visitor never republishes
    // somebody else's decisions as their own.
    if (saved && entries.length) await persist(entries);
    // Nobody should have to upload the dataset: every load merges whatever
    // file the server is serving, so swapping that file reaches reviewers
    // without touching their existing decisions.
    await loadServerDataset();
  }
  async function loadServerDataset() {
    try {
      const response = await fetch('examples.json');
      if (!response.ok) return;
      const merged = R.mergeEntries(entries, R.parseFile(await response.text()).entries);
      // mergeEntries keeps decisions already made, so swapping the dataset on
      // the server adds the new examples without losing earlier reviews.
      if (!merged.added) return;
      await persist(merged.entries);
      entries = merged.entries;
      filter = 'pending';
      selected = 0;
      loadedFromServer = merged.added;
      notice(`Loaded ${merged.added} ${merged.added === 1 ? 'example' : 'examples'} from the server.`);
    } catch { /* importing a file by hand still works */ }
  }
  async function loadClientId() {
    const existing = await new Promise((resolve, reject) => {
      const request = database.transaction('workspace').objectStore('workspace').get('client');
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    if (typeof existing === 'string' && existing) return existing;
    const created = (self.crypto && self.crypto.randomUUID ? self.crypto.randomUUID() : `${Date.now()}${Math.random().toString(16).slice(2)}`)
      .replace(/[^A-Za-z0-9_-]/g, '')
      .slice(0, 64);
    await new Promise((resolve, reject) => {
      const transaction = database.transaction('workspace', 'readwrite');
      transaction.objectStore('workspace').put(created, 'client');
      transaction.oncomplete = resolve;
      transaction.onerror = () => reject(transaction.error);
    });
    return created;
  }
  // Decisions live in this browser's IndexedDB and are mirrored to the server, so
  // a fresh browser, a phone, or a reloaded profile picks up the shared progress.
  async function mergeServer() {
    if (!clientId) return;
    try {
      const response = await fetch(`api/session?client=${encodeURIComponent(clientId)}`, { headers: { accept: 'application/json' } });
      if (!response.ok) return;
      // A successful read means the server is reachable and holds this state.
      serverSaved = true;
      const remote = JSON.parse(await response.text());
      if (!remote || !Array.isArray(remote.entries) || !remote.entries.length) return;
      const merged = R.mergeEntries(entries, R.parseFile(JSON.stringify(remote)).entries);
      const restored = merged.added + merged.restored;
      if (!restored) return;
      await persist(merged.entries);
      entries = merged.entries;
      syncedFromServer = restored;
      notice(`Restored ${restored} example${restored === 1 ? '' : 's'} from server progress.`);
    } catch { /* offline: the local copy stays authoritative */ }
  }
  async function syncServer(candidate) {
    if (!clientId) return;
    try {
      const response = await fetch(`api/session?client=${encodeURIComponent(clientId)}`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: R.session(candidate) });
      serverSaved = response.ok;
    } catch { serverSaved = false; }
  }
  async function persist(candidate) {
    if (!database) return;
    await new Promise((resolve, reject) => {
      const transaction = database.transaction('workspace', 'readwrite');
      transaction.objectStore('workspace').put(R.session(candidate), 'session');
      transaction.oncomplete = resolve;
      transaction.onerror = () => reject(transaction.error || new Error('Could not save this review.'));
      transaction.onabort = () => reject(transaction.error || new Error('Saving was interrupted.'));
    });
    await syncServer(candidate);
  }
  async function task(action) {
    if (busy) return;
    busy = true;
    // Do not re-render the form before capturing a typed review note.
    document.querySelectorAll('button').forEach(button => { button.disabled = true; });
    $('file-input').disabled = true;
    try { await action(); }
    catch (error) { notice(error.message || 'That operation failed. Your existing reviews have been kept.', true); }
    finally { busy = false; render(); }
  }
  async function importText(text, filename) {
    const parsed = R.parseFile(text);
    const merged = R.mergeEntries(entries, parsed.entries);
    await persist(merged.entries);
    entries = merged.entries;
    history.length = 0;
    filter = 'pending';
    selected = entries.findIndex(e => !e.decision);
    if (selected < 0) selected = 0;
    notice(`${filename}: ${merged.added} added, ${merged.restored} decisions restored, ${merged.duplicates} duplicates skipped.`);
  }
  async function importFile(file) {
    if (!file) return;
    await task(async () => {
      if (file.size > R.MAX_BYTES) throw new Error('Use a file smaller than 10 MB.');
      await importText(await file.text(), file.name);
    });
  }
  async function review(decision) {
    const index = selected;
    const reason = $('review-reason').value;
    await task(async () => {
      const before = structuredClone(entries[index]);
      const candidate = R.decide(entries, index, decision, reason);
      await persist(candidate);
      entries = candidate;
      history.push({ index, before });
      if (decision && filter !== 'pending') {
        const indices = visibleIndices();
        selected = indices[indices.indexOf(index) + 1] ?? index;
      }
      notice(decision === 'approve' ? 'Approved. Included in both dataset exports.' : decision === 'deny' ? 'Denied. Included only in the classifier export.' : 'Returned to pending. Removed from both dataset exports.');
    });
  }
  function download(content, name, type) {
    $('export-menu').open = false;
    const url = URL.createObjectURL(new Blob([content], { type }));
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = name;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
    notice(`Downloaded ${name}. Your reviews remain saved in this browser.`);
  }
  $('file-input').addEventListener('change', async event => { await importFile(event.target.files[0]); event.target.value = ''; });
  document.querySelectorAll('label[for="file-input"]').forEach(label => {
    label.tabIndex = 0;
    label.setAttribute('role', 'button');
    label.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); if (!busy) $('file-input').click(); } });
  });
  const zone = $('drop-zone');
  for (const name of ['dragenter', 'dragover']) zone.addEventListener(name, event => { event.preventDefault(); zone.classList.add('dragging'); });
  for (const name of ['dragleave', 'drop']) zone.addEventListener(name, event => { event.preventDefault(); zone.classList.remove('dragging'); });
  zone.addEventListener('drop', event => { if (event.dataTransfer.files.length !== 1) notice('Choose one file at a time.', true); else importFile(event.dataTransfer.files[0]); });
  // Prevent a dropped file outside the target from navigating away from unsaved work.
  window.addEventListener('dragover', event => event.preventDefault());
  window.addEventListener('drop', event => event.preventDefault());
  $('load-sample').addEventListener('click', () => task(async () => {
    const response = await fetch('examples.json');
    if (!response.ok) throw new Error('Could not load the sample. Import a local JSON file instead.');
    await importText(await response.text(), 'examples.json');
  }));
  $('approve').addEventListener('click', () => review('approve'));
  $('deny').addEventListener('click', () => review('deny'));
  $('clear-decision').addEventListener('click', () => review(null));
  $('undo').addEventListener('click', () => task(async () => {
    const last = history[history.length - 1];
    if (!last) return;
    const candidate = structuredClone(entries);
    candidate[last.index] = last.before;
    await persist(candidate);
    entries = candidate;
    history.pop();
    selected = last.index;
    filter = 'all';
    notice('Last decision undone. Dataset exports reflect the change.');
  }));
  document.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click', () => { filter = button.dataset.filter; render(); }));
  $('see-all').addEventListener('click', () => { filter = 'all'; render(); });
  for (const [id, offset] of [['previous', -1], ['next', 1]]) $(id).addEventListener('click', () => {
    const indices = visibleIndices();
    selected = indices[indices.indexOf(selected) + offset] ?? selected;
    render();
  });
  $('export-needle').addEventListener('click', () => download(R.needle(entries), 'needle-approved.jsonl', 'application/x-ndjson'));
  $('export-classifier').addEventListener('click', () => download(R.classifier(entries), 'classifier-labeled.jsonl', 'application/x-ndjson'));
  $('export-session').addEventListener('click', () => download(R.session(entries), 'zoairk-review-session.json', 'application/json'));
  document.addEventListener('click', event => { if (!$('export-menu').contains(event.target)) $('export-menu').open = false; });
  window.addEventListener('beforeunload', event => { if (entries.length && !database) { event.preventDefault(); event.returnValue = ''; } });
  (async () => {
    try { await openStorage(); if (entries.length && !syncedFromServer && !loadedFromServer) notice('Welcome back. Your review progress has been restored.'); }
    catch (error) { database = null; notice('Could not restore local storage. You can still review, but export a session before leaving. ' + error.message, true); }
    finally { busy = false; render(); }
  })();
})();
