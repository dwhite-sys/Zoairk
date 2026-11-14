'use strict';
const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { createServer } = require('../scripts/serve.cjs');
const R = require('../review.js');
let server, base;
before(async () => {
  server = createServer();
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  base = 'http://127.0.0.1:' + server.address().port;
});
after(async () => { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); });
test('serves the app and its scripts with correct content types', async () => {
  for (const [route, type] of [['/', 'text/html'], ['/app.js', 'application/javascript'], ['/review.js', 'application/javascript'], ['/styles.css', 'text/css']]) {
    const response = await fetch(base + route);
    assert.equal(response.status, 200);
    assert.ok(response.headers.get('content-type').startsWith(type));
    assert.ok((await response.text()).length > 100);
    assert.ok(response.headers.get('content-security-policy').includes("object-src 'none'"));
  }
});
test('sample import, labeling, and both dataset exports integrate end to end', async () => {
  const response = await fetch(base + '/examples.json');
  let entries = R.parseFile(await response.text()).entries;
  entries = R.decide(entries, 0, 'approve');
  entries = R.decide(entries, 1, 'deny', 'incorrect');
  const restored = R.parseFile(R.session(entries)).entries;
  assert.equal(R.counts(restored).approved, 1);
  assert.equal(R.counts(restored).denied, 1);
  assert.equal(JSON.parse(R.needle(restored)).answers[0].arguments.action, 'unlock');
  assert.equal(R.classifier(restored).trim().split('\n').length, 2);
});
test('serves under an optional path prefix and redirects the bare prefix', async () => {
  const prefixed = createServer({ prefix: '/needle-training' });
  await new Promise(resolve => prefixed.listen(0, '127.0.0.1', resolve));
  const origin = 'http://127.0.0.1:' + prefixed.address().port;
  try {
    for (const [route, type] of [['/needle-training/', 'text/html'], ['/needle-training/app.js', 'application/javascript'], ['/needle-training/styles.css', 'text/css'], ['/needle-training/examples.json', 'application/json']]) {
      const response = await fetch(origin + route);
      assert.equal(response.status, 200, route);
      assert.ok(response.headers.get('content-type').startsWith(type), route);
    }
    const bare = await fetch(origin + '/needle-training?x=1', { redirect: 'manual' });
    assert.equal(bare.status, 308);
    assert.equal(bare.headers.get('location'), '/needle-training/?x=1');
    for (const route of ['/', '/styles.css', '/needle-trainingx/', '/needle-training/%2e%2e/README.md']) {
      assert.equal((await fetch(origin + route)).status, 404, route);
    }
  } finally {
    prefixed.closeAllConnections();
    await new Promise(resolve => prefixed.close(resolve));
  }
});
test('normalizes prefix values passed as configuration', () => {
  const { normalizePrefix } = require('../scripts/serve.cjs');
  assert.equal(normalizePrefix(undefined), '');
  assert.equal(normalizePrefix('  '), '');
  assert.equal(normalizePrefix('needle-training'), '/needle-training');
  assert.equal(normalizePrefix('/needle-training/'), '/needle-training');
  assert.equal(normalizePrefix('/a/b//'), '/a/b');
});
test('stores review sessions and serves them back to another browser', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'zoairk-review-'));
  const previous = process.env.REVIEW_DATA_DIR;
  process.env.REVIEW_DATA_DIR = dir;
  const api = createServer({ prefix: '/needle-training' });
  await new Promise(resolve => api.listen(0, '127.0.0.1', resolve));
  const origin = 'http://127.0.0.1:' + api.address().port;
  const clientA = 'clientaaaaaaaaaaa';
  const clientB = 'clientbbbbbbbbbbb';
  try {
    const entries = R.parseFile(await fs.readFile(path.join(__dirname, '..', 'examples.json'), 'utf8')).entries;
    const decided = R.decide(R.decide(entries, 0, 'approve'), 1, 'deny', 'wrong order of calls');
    const post = await fetch(`${origin}/needle-training/api/session?client=${clientA}`, {
      method: 'POST', headers: { 'content-type': 'application/json' }, body: R.session(decided)
    });
    assert.equal(post.status, 200);
    assert.equal((await post.json()).saved, decided.length);
    // The snapshot is on disk, so it survives a restart.
    const stored = JSON.parse(await fs.readFile(path.join(dir, `${clientA}.json`), 'utf8'));
    assert.equal(stored.entries[0].decision, 'approve');
    assert.ok(Number.isFinite(Date.parse(stored.savedAt)));

    // A second browser sees the first browser's decisions.
    const seen = await (await fetch(`${origin}/needle-training/api/session?client=${clientB}`)).json();
    assert.equal(R.counts(seen.entries).approved, 1);
    assert.equal(R.counts(seen.entries).denied, 1);
    assert.equal(seen.entries[1].reason, 'wrong order of calls');
    assert.equal(JSON.parse(R.needle(seen.entries)).answers[0].arguments.action, 'unlock');

    // An undo is a state change, not an event: it propagates, so the other
    // browser now sees this example as pending. Conflicting edits are the only
    // thing a browser's own snapshot wins over.
    await fetch(`${origin}/needle-training/api/session?client=${clientA}`, {
      method: 'POST', headers: { 'content-type': 'application/json' }, body: R.session(R.decide(decided, 0, null))
    });
    const own = await (await fetch(`${origin}/needle-training/api/session?client=${clientA}`)).json();
    assert.equal(R.counts(own.entries).approved, 0);
    const other = await (await fetch(`${origin}/needle-training/api/session?client=${clientB}`)).json();
    assert.equal(R.counts(other.entries).approved, 0);
    assert.equal(R.counts(other.entries).denied, 1);
  } finally {
    api.closeAllConnections();
    await new Promise(resolve => api.close(resolve));
    if (previous === undefined) delete process.env.REVIEW_DATA_DIR; else process.env.REVIEW_DATA_DIR = previous;
    await fs.rm(dir, { recursive: true, force: true });
  }
});
test('every accepted session rewrites the dataset files on disk', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'zoairk-review-'));
  const previous = process.env.REVIEW_DATA_DIR;
  process.env.REVIEW_DATA_DIR = dir;
  const api = createServer();
  await new Promise(resolve => api.listen(0, '127.0.0.1', resolve));
  const origin = 'http://127.0.0.1:' + api.address().port;
  const client = 'clientexporttest01';
  const read = name => fs.readFile(path.join(dir, 'exports', name), 'utf8');
  try {
    const entries = R.parseFile(await fs.readFile(path.join(__dirname, '..', 'examples.json'), 'utf8')).entries;
    const decided = R.decide(R.decide(entries, 0, 'approve'), 1, 'deny', 'nope');
    const posted = await (await fetch(`${origin}/api/session?client=${client}`, {
      method: 'POST', headers: { 'content-type': 'application/json' }, body: R.session(decided)
    })).json();
    assert.equal(posted.exports.approved, 1);
    assert.equal(posted.exports.denied, 1);

    // Approved-only for Needle, both labels for the classifier.
    assert.equal((await read('needle-approved.jsonl')).trim().split('\n').length, 1);
    assert.equal((await read('classifier-labeled.jsonl')).trim().split('\n').length, 2);
    assert.equal(JSON.parse((await read('classifier-labeled.jsonl')).trim().split('\n')[1]).review_reason, 'nope');
    assert.equal(R.parseFile(await read('zoairk-review-session.json')).entries.length, entries.length);

    // Undo must remove the row, not leave a stale approval behind.
    await fetch(`${origin}/api/session?client=${client}`, {
      method: 'POST', headers: { 'content-type': 'application/json' }, body: R.session(R.decide(R.decide(decided, 0, null), 1, null))
    });
    assert.equal((await read('needle-approved.jsonl')).trim(), '');
    assert.equal((await read('classifier-labeled.jsonl')).trim(), '');

    // The HTTP exports serve the same merged content.
    const exported = await fetch(`${origin}/api/exports/needle.jsonl`);
    assert.equal(exported.status, 200);
    assert.match(exported.headers.get('content-disposition'), /needle-approved\.jsonl/);
    assert.equal(await exported.text(), await read('needle-approved.jsonl'));
    assert.equal((await fetch(`${origin}/api/exports/classifier.jsonl`, { method: 'POST' })).status, 405);
  } finally {
    api.closeAllConnections();
    await new Promise(resolve => api.close(resolve));
    if (previous === undefined) delete process.env.REVIEW_DATA_DIR; else process.env.REVIEW_DATA_DIR = previous;
    await fs.rm(dir, { recursive: true, force: true });
  }
});
test('rejects bad sessions and client ids without writing anything', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'zoairk-review-'));
  const previous = process.env.REVIEW_DATA_DIR;
  process.env.REVIEW_DATA_DIR = dir;
  const api = createServer();
  await new Promise(resolve => api.listen(0, '127.0.0.1', resolve));
  const origin = 'http://127.0.0.1:' + api.address().port;
  try {
    assert.equal((await fetch(`${origin}/api/session`, { method: 'POST', body: '{}' })).status, 400);
    assert.equal((await fetch(`${origin}/api/session?client=${encodeURIComponent('../etc/passwd')}`, { method: 'POST', body: '{}' })).status, 400);
    assert.equal((await fetch(`${origin}/api/session?client=clientcccccccccccc`, { method: 'POST', body: '{"query":"x"}' })).status, 400);
    assert.equal((await fetch(`${origin}/api/session?client=clientcccccccccccc`, { method: 'POST', body: 'not json' })).status, 400);
    assert.deepEqual(await fs.readdir(dir), []);
  } finally {
    api.closeAllConnections();
    await new Promise(resolve => api.close(resolve));
    if (previous === undefined) delete process.env.REVIEW_DATA_DIR; else process.env.REVIEW_DATA_DIR = previous;
    await fs.rm(dir, { recursive: true, force: true });
  }
});
test('does not expose repository files, traversal, or write endpoints', async () => {
  for (const route of ['/.git/config', '/AGENTS.md', '/package.json', '/%2e%2e/README.md', '/unknown']) assert.equal((await fetch(base + route)).status, 404);
  assert.equal((await fetch(base + '/', { method: 'POST', body: 'data' })).status, 405);
  const head = await fetch(base + '/', { method: 'HEAD' });
  assert.equal(head.status, 200);
  assert.equal(await head.text(), '');
});
