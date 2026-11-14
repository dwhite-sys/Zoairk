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
  assert.deepEqual(JSON.parse(R.needle(restored)), entries[0].example);
  assert.equal(R.classifier(restored).trim().split('\n').length, 2);
});
test('serves the dataset named by EXAMPLES_FILE and rejects a bad one', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'zoairk-data-'));
  const previous = process.env.EXAMPLES_FILE;
  const api = createServer();
  await new Promise(resolve => api.listen(0, '127.0.0.1', resolve));
  const origin = 'http://127.0.0.1:' + api.address().port;
  try {
    const source = JSON.parse(await fs.readFile(path.join(__dirname, '..', 'examples.json'), 'utf8'));
    const single = path.join(dir, 'mine.json');
    await fs.writeFile(single, JSON.stringify([source[3]]));
    process.env.EXAMPLES_FILE = single;
    const served = await fetch(`${origin}/examples.json`);
    assert.equal(served.status, 200);
    const body = await served.json();
    assert.equal(body.length, 1);
    assert.equal(body[0].query, source[3].query);

    // JSONL works too, since the importer accepts it.
    const jsonl = path.join(dir, 'mine.jsonl');
    await fs.writeFile(jsonl, source.slice(0, 2).map(item => JSON.stringify(item)).join('\n'));
    process.env.EXAMPLES_FILE = jsonl;
    assert.equal((await (await fetch(`${origin}/examples.json`)).json()).length, 2);

    // A dataset the importer would reject fails loudly here instead of in every browser.
    const broken = path.join(dir, 'broken.json');
    await fs.writeFile(broken, '{"nope":true}');
    process.env.EXAMPLES_FILE = broken;
    const rejected = await fetch(`${origin}/examples.json`);
    assert.equal(rejected.status, 500);
    assert.match((await rejected.json()).error, /Could not load the dataset/);

    process.env.EXAMPLES_FILE = path.join(dir, 'missing.json');
    assert.equal((await fetch(`${origin}/examples.json`)).status, 500);
  } finally {
    api.closeAllConnections();
    await new Promise(resolve => api.close(resolve));
    if (previous === undefined) delete process.env.EXAMPLES_FILE; else process.env.EXAMPLES_FILE = previous;
    await fs.rm(dir, { recursive: true, force: true });
  }
});
test('EXAMPLES_DIR serves the union of every batch, keeping older ones', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'zoairk-batches-'));
  const previousFile = process.env.EXAMPLES_FILE;
  const previousDir = process.env.EXAMPLES_DIR;
  delete process.env.EXAMPLES_FILE;
  process.env.EXAMPLES_DIR = dir;
  const api = createServer();
  await new Promise(resolve => api.listen(0, '127.0.0.1', resolve));
  const origin = 'http://127.0.0.1:' + api.address().port;
  try {
    const source = JSON.parse(await fs.readFile(path.join(__dirname, '..', 'examples.json'), 'utf8'));
    assert.equal((await fetch(`${origin}/examples.json`)).status, 500);

    await fs.writeFile(path.join(dir, '01-first.json'), JSON.stringify(source.slice(0, 2)));
    assert.equal((await (await fetch(`${origin}/examples.json`)).json()).length, 2);

    // A later batch adds to the queue; the first batch is still served.
    await fs.writeFile(path.join(dir, '02-second.jsonl'), source.slice(2, 4).map(item => JSON.stringify(item)).join('\n'));
    const both = await (await fetch(`${origin}/examples.json`)).json();
    assert.equal(both.length, 4);
    assert.deepEqual(both.map(item => item.query), source.slice(0, 4).map(item => item.query));

    // An example repeated across batches is served once.
    await fs.writeFile(path.join(dir, '03-repeat.json'), JSON.stringify(source.slice(0, 1)));
    assert.equal((await (await fetch(`${origin}/examples.json`)).json()).length, 4);

    // A broken batch fails loudly rather than silently shrinking the dataset.
    await fs.writeFile(path.join(dir, '04-broken.json'), '{"nope":true}');
    assert.equal((await fetch(`${origin}/examples.json`)).status, 500);
  } finally {
    api.closeAllConnections();
    await new Promise(resolve => api.close(resolve));
    if (previousFile === undefined) delete process.env.EXAMPLES_FILE; else process.env.EXAMPLES_FILE = previousFile;
    if (previousDir === undefined) delete process.env.EXAMPLES_DIR; else process.env.EXAMPLES_DIR = previousDir;
    await fs.rm(dir, { recursive: true, force: true });
  }
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
test('keeps one shared workspace that every browser reads and writes', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'zoairk-review-'));
  const previous = process.env.REVIEW_DATA_DIR;
  process.env.REVIEW_DATA_DIR = dir;
  const api = createServer({ prefix: '/needle-training' });
  await new Promise(resolve => api.listen(0, '127.0.0.1', resolve));
  const origin = 'http://127.0.0.1:' + api.address().port;
  const decide = body => fetch(`${origin}/needle-training/api/decision`, {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body)
  });
  try {
    const entries = R.parseFile(await fs.readFile(path.join(__dirname, '..', 'examples.json'), 'utf8')).entries;
    assert.deepEqual((await (await fetch(`${origin}/needle-training/api/session`)).json()).entries, []);

    // Registering examples is additive and keeps the decisions they arrive with.
    const post = await fetch(`${origin}/needle-training/api/session`, {
      method: 'POST', headers: { 'content-type': 'application/json' }, body: R.session(R.decide(entries, 0, 'approve'))
    });
    assert.equal(post.status, 200);
    assert.equal((await post.json()).added, entries.length);

    // The state file is on disk, so a restart keeps it.
    const stored = JSON.parse(await fs.readFile(path.join(dir, 'state.json'), 'utf8'));
    assert.equal(stored.entries.length, entries.length);

    // Any browser sees the same workspace; there is no per-browser view.
    const seen = await (await fetch(`${origin}/needle-training/api/session`)).json();
    assert.equal(R.counts(seen.entries).approved, 1);

    // A decision from "another browser" is what the shared workspace now says.
    const key = R.stable(entries[1].example);
    assert.equal((await decide({ key, example: entries[1].example, decision: 'deny', reason: 'wrong order' })).status, 200);
    const after = await (await fetch(`${origin}/needle-training/api/session`)).json();
    assert.equal(R.counts(after.entries).denied, 1);
    assert.equal(after.entries[1].reason, 'wrong order');
    assert.deepEqual(JSON.parse(R.needle(after.entries)), entries[0].example);

    // An example the server has never seen is accepted rather than rejected.
    const fresh = entries[5].example;
    assert.equal((await decide({ key: R.stable(fresh), example: fresh, decision: 'approve' })).status, 200);
    assert.equal(R.counts((await (await fetch(`${origin}/needle-training/api/session`)).json()).entries).approved, 2);

    // Clearing a decision is global too.
    await decide({ key, decision: null });
    assert.equal(R.counts((await (await fetch(`${origin}/needle-training/api/session`)).json()).entries).denied, 0);

    // Malformed decisions are refused.
    assert.equal((await decide({ key, decision: 'maybe' })).status, 400);
    assert.equal((await decide({ decision: 'approve' })).status, 400);
    assert.equal((await fetch(`${origin}/needle-training/api/decision`)).status, 405);
  } finally {
    api.closeAllConnections();
    await new Promise(resolve => api.close(resolve));
    if (previous === undefined) delete process.env.REVIEW_DATA_DIR; else process.env.REVIEW_DATA_DIR = previous;
    await fs.rm(dir, { recursive: true, force: true });
  }
});
test('every decision rewrites the dataset files on disk', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'zoairk-review-'));
  const previous = process.env.REVIEW_DATA_DIR;
  process.env.REVIEW_DATA_DIR = dir;
  const api = createServer();
  await new Promise(resolve => api.listen(0, '127.0.0.1', resolve));
  const origin = 'http://127.0.0.1:' + api.address().port;
  const read = name => fs.readFile(path.join(dir, 'exports', name), 'utf8');
  const decide = body => fetch(`${origin}/api/decision`, {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body)
  });
  try {
    const entries = R.parseFile(await fs.readFile(path.join(__dirname, '..', 'examples.json'), 'utf8')).entries;
    await fetch(`${origin}/api/session`, {
      method: 'POST', headers: { 'content-type': 'application/json' }, body: R.session(entries)
    });
    await decide({ key: R.stable(entries[0].example), example: entries[0].example, decision: 'approve' });
    await decide({ key: R.stable(entries[1].example), example: entries[1].example, decision: 'deny', reason: 'nope' });

    assert.equal((await read('needle-approved.jsonl')).trim().split('\n').length, 1);
    assert.equal((await read('classifier-labeled.jsonl')).trim().split('\n').length, 2);
    assert.equal(JSON.parse((await read('classifier-labeled.jsonl')).trim().split('\n')[1]).review_reason, 'nope');

    // Undo must remove the row, not leave a stale label behind.
    await decide({ key: R.stable(entries[0].example), decision: null });
    await decide({ key: R.stable(entries[1].example), decision: null });
    assert.equal((await read('needle-approved.jsonl')).trim(), '');
    assert.equal((await read('classifier-labeled.jsonl')).trim(), '');

    // The HTTP exports serve the same content as the files.
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
