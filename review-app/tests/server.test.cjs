'use strict';
const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
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
test('does not expose repository files, traversal, or write endpoints', async () => {
  for (const route of ['/.git/config', '/AGENTS.md', '/package.json', '/%2e%2e/README.md', '/unknown']) assert.equal((await fetch(base + route)).status, 404);
  assert.equal((await fetch(base + '/', { method: 'POST', body: 'data' })).status, 405);
  const head = await fetch(base + '/', { method: 'HEAD' });
  assert.equal(head.status, 200);
  assert.equal(await head.text(), '');
});
