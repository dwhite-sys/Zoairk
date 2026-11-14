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
test('does not expose repository files, traversal, or write endpoints', async () => {
  for (const route of ['/.git/config', '/AGENTS.md', '/package.json', '/%2e%2e/README.md', '/unknown']) assert.equal((await fetch(base + route)).status, 404);
  assert.equal((await fetch(base + '/', { method: 'POST', body: 'data' })).status, 405);
  const head = await fetch(base + '/', { method: 'HEAD' });
  assert.equal(head.status, 200);
  assert.equal(await head.text(), '');
});
