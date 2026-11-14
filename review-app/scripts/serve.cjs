'use strict';
const http = require('node:http');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const root = path.resolve(__dirname, '..');
const R = require(path.join(root, 'review.js'));
const files = new Map([
  ['/', ['index.html', 'text/html; charset=utf-8']],
  ['/index.html', ['index.html', 'text/html; charset=utf-8']],
  ['/styles.css', ['styles.css', 'text/css; charset=utf-8']],
  ['/review.js', ['review.js', 'application/javascript; charset=utf-8']],
  ['/app.js', ['app.js', 'application/javascript; charset=utf-8']],
  ['/examples.json', ['examples.json', 'application/json; charset=utf-8']]
]);
const MAX_BODY = 10 * 1024 * 1024;

function normalizePrefix(value) {
  if (!value) return '';
  const raw = String(value).trim();
  if (!raw) return '';
  const prefixed = raw.startsWith('/') ? raw : `/${raw}`;
  return prefixed.replace(/\/+$/, '');
}

// Review sessions are kept outside the repository so a clone stays clean.
function dataDir() {
  return process.env.REVIEW_DATA_DIR || path.join(os.homedir(), '.local', 'share', 'zoairk-review');
}
// The dataset reviewers work through lives on this machine. Point EXAMPLES_FILE
// at it and the page loads it; nobody has to upload a file.
function examplesFile() {
  return process.env.EXAMPLES_FILE ? path.resolve(process.env.EXAMPLES_FILE) : path.join(root, 'examples.json');
}
// Every .json/.jsonl file in EXAMPLES_DIR is served as one dataset, so dropping
// in a new batch adds to the queue and never drops examples added earlier.
function datasetDir() {
  return process.env.EXAMPLES_DIR ? path.resolve(process.env.EXAMPLES_DIR) : null;
}
async function readDataset() {
  const dir = datasetDir();
  if (!dir) {
    const file = examplesFile();
    const parsed = R.parseFile(await fs.readFile(file, 'utf8'));
    return { examples: parsed.entries.map(entry => entry.example), source: file };
  }
  const names = (await fs.readdir(dir)).filter(name => /\.(json|jsonl)$/i.test(name)).sort();
  if (!names.length) throw new Error(`No .json or .jsonl files in ${dir}.`);
  let entries = [];
  for (const name of names) {
    const parsed = R.parseFile(await fs.readFile(path.join(dir, name), 'utf8'));
    // mergeEntries deduplicates, so the same example appearing in two batches
    // is served once.
    entries = R.mergeEntries(entries, parsed.entries).entries;
  }
  return { examples: entries.map(entry => entry.example), source: `${dir} (${names.length} file${names.length === 1 ? '' : 's'})` };
}
function validClient(value) {
  return typeof value === 'string' && /^[A-Za-z0-9_-]{8,64}$/.test(value);
}
function json(res, status, payload) {
  const body = JSON.stringify(payload);
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Content-Length': Buffer.byteLength(body) });
  res.end(body);
}
async function readBody(req) {
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > MAX_BODY) throw new Error('Request body is too large.');
    chunks.push(chunk);
  }
  return Buffer.concat(chunks).toString('utf8');
}
async function readSnapshots() {
  let names = [];
  try { names = await fs.readdir(dataDir()); } catch { return []; }
  const snapshots = [];
  for (const name of names) {
    if (!name.endsWith('.json')) continue;
    try {
      const snapshot = JSON.parse(await fs.readFile(path.join(dataDir(), name), 'utf8'));
      if (snapshot && typeof snapshot.client === 'string' && Array.isArray(snapshot.entries)) snapshots.push(snapshot);
    } catch { /* ignore a foreign or half-written file */ }
  }
  return snapshots.sort((a, b) => String(a.savedAt).localeCompare(String(b.savedAt)));
}
async function mergeFor(client) {
  const snapshots = await readSnapshots();
  const own = snapshots.filter(s => s.client === client).reverse();
  const others = snapshots.filter(s => s.client !== client).reverse();
  let entries = [];
  // Newest first, with this browser's own snapshot ahead of every other one:
  // mergeEntries lets an existing decision win, and local edits (including
  // undo) have to survive a refetch.
  for (const snapshot of [...own, ...others]) {
    try { entries = R.mergeEntries(entries, snapshot.entries).entries; } catch { /* skip an oversized snapshot */ }
  }
  return { format: 'zoairk-review-session', version: 1, entries };
}
async function handleExamples(req, res) {
  if (!['GET', 'HEAD'].includes(req.method)) { json(res, 405, { error: 'Method not allowed.' }); return; }
  let dataset;
  try { dataset = await readDataset(); }
  catch (error) { json(res, 500, { error: `Could not load the dataset: ${error.message}` }); return; }
  const body = Buffer.from(JSON.stringify(dataset.examples), 'utf8');
  res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8', 'Content-Length': body.length, 'X-Zoairk-Dataset': dataset.source });
  res.end(req.method === 'HEAD' ? undefined : body);
}
async function handleSession(req, res, url) {
  const client = url.searchParams.get('client') || '';
  if (!validClient(client)) { json(res, 400, { error: 'A valid client id is required.' }); return; }
  if (req.method === 'POST') {
    let parsed;
    try { parsed = R.parseFile(await readBody(req)); }
    catch (error) { json(res, 400, { error: error.message }); return; }
    if (!parsed.session) { json(res, 400, { error: 'Send a review session file.' }); return; }
    const snapshot = { client, savedAt: new Date().toISOString(), entries: parsed.entries };
    const target = path.join(dataDir(), `${client}.json`);
    const temp = `${target}.${process.pid}.tmp`;
    try {
      await fs.mkdir(dataDir(), { recursive: true });
      await fs.writeFile(temp, JSON.stringify(snapshot));
      await fs.rename(temp, target);
    } catch (error) { json(res, 500, { error: 'Could not save the review session.' }); return; }
    const written = await materialize();
    json(res, 200, { saved: snapshot.entries.length, savedAt: snapshot.savedAt, exports: written });
    return;
  }
  if (!['GET', 'HEAD'].includes(req.method)) { json(res, 405, { error: 'Method not allowed.' }); return; }
  json(res, 200, await mergeFor(client));
}
// Union of every browser's snapshot, newest first: the exports describe the
// dataset as a whole rather than one reviewer's view.
async function mergeAll() {
  const snapshots = (await readSnapshots()).reverse();
  let entries = [];
  for (const snapshot of snapshots) {
    try { entries = R.mergeEntries(entries, snapshot.entries).entries; } catch { /* skip an oversized snapshot */ }
  }
  return entries;
}
const exportRoutes = new Map([
  ['/api/exports/needle.jsonl', ['needle-approved.jsonl', 'application/x-ndjson', entries => R.needle(entries)]],
  ['/api/exports/classifier.jsonl', ['classifier-labeled.jsonl', 'application/x-ndjson', entries => R.classifier(entries)]],
  ['/api/exports/session.json', ['zoairk-review-session.json', 'application/json', entries => R.session(entries)]]
]);
async function handleExport(req, res, format) {
  if (!['GET', 'HEAD'].includes(req.method)) { json(res, 405, { error: 'Method not allowed.' }); return; }
  const [filename, type, build] = format;
  let body;
  try { body = build(await mergeAll()); }
  catch { json(res, 500, { error: 'Could not build the export.' }); return; }
  const buffer = Buffer.from(body, 'utf8');
  res.writeHead(200, {
    'Content-Type': `${type}; charset=utf-8`,
    'Content-Length': buffer.length,
    'Content-Disposition': `attachment; filename="${filename}"`
  });
  res.end(req.method === 'HEAD' ? undefined : buffer);
}
// Every accepted session rewrites the dataset files, so what sits on disk is
// always current and can be copied off without opening a browser.
async function materialize() {
  const entries = await mergeAll();
  const dir = path.join(dataDir(), 'exports');
  try {
    await fs.mkdir(dir, { recursive: true });
    for (const [filename, , build] of exportRoutes.values()) {
      const target = path.join(dir, filename);
      const temp = `${target}.${process.pid}.tmp`;
      await fs.writeFile(temp, build(entries));
      await fs.rename(temp, target);
    }
    return { directory: dir, approved: entries.filter(e => e.decision === 'approve').length, denied: entries.filter(e => e.decision === 'deny').length };
  } catch { return null; }
}

function createServer({ prefix = normalizePrefix(process.env.APP_PREFIX) } = {}) {
  return http.createServer(async (req, res) => {
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('Referrer-Policy', 'no-referrer');
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'");
    const url = new URL(req.url, 'http://localhost');
    let route = url.pathname;
    if (prefix) {
      if (route === prefix) {
        res.writeHead(308, { Location: `${prefix}/${url.search}` });
        res.end();
        return;
      }
      if (!route.startsWith(`${prefix}/`)) {
        res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
        res.end('Not found');
        return;
      }
      route = route.slice(prefix.length);
    }
    if (route === '/examples.json') { await handleExamples(req, res); return; }
    if (route === '/api/session') { await handleSession(req, res, url); return; }
    if (exportRoutes.has(route)) { await handleExport(req, res, exportRoutes.get(route)); return; }
    if (!['GET', 'HEAD'].includes(req.method)) { res.writeHead(405, { Allow: 'GET, HEAD' }); res.end('Method not allowed'); return; }
    const file = files.get(route);
    if (!file) { res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' }); res.end('Not found'); return; }
    try {
      const content = await fs.readFile(path.join(root, file[0]));
      res.writeHead(200, { 'Content-Type': file[1], 'Content-Length': content.length });
      res.end(req.method === 'HEAD' ? undefined : content);
    } catch { res.writeHead(500); res.end('Could not read application asset.'); }
  });
}
module.exports = { createServer, normalizePrefix, dataDir };
if (require.main === module) {
  const args = process.argv.slice(2);
  const hostIndex = args.indexOf('--host');
  const host = hostIndex >= 0 ? args[hostIndex + 1] : '127.0.0.1';
  const port = Number(process.env.PORT || 3000);
  if (!host || !Number.isInteger(port) || port < 0 || port > 65535) { console.error('Use a valid --host and PORT (0–65535).'); process.exit(1); }
  const server = createServer();
  server.on('error', error => { console.error(`Could not start Zoairk: ${error.message}`); process.exitCode = 1; });
  server.listen(port, host, () => {
    const actualPort = server.address().port;
    const prefix = normalizePrefix(process.env.APP_PREFIX);
    console.log(`Zoairk review: http://localhost:${actualPort}${prefix}/`);
    console.log(`Review sessions: ${dataDir()}`);
    console.log(`Dataset: ${examplesFile()}`);
    if (host === '0.0.0.0') {
      for (const list of Object.values(os.networkInterfaces())) for (const net of list || []) if (net.family === 'IPv4' && !net.internal) console.log(`Same Wi-Fi / LAN: http://${net.address}:${actualPort}`);
    }
  });
}
