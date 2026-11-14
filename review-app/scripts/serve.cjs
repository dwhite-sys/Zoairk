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
// Where the generated dataset files go; point EXPORT_DIR inside the repository
// so a `git add` carries them to the rest of the team.
function exportDir() {
  return process.env.EXPORT_DIR ? path.resolve(process.env.EXPORT_DIR) : path.join(dataDir(), 'exports');
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
// ---- shared review state -------------------------------------------------
// One workspace for the whole team: every browser reads and writes the same
// entries, so a decision made on one device is what everybody else sees.
function stateFile() {
  return path.join(dataDir(), 'state.json');
}
function sessionOf(state) {
  return { format: 'zoairk-review-session', version: 1, entries: state.entries };
}
async function saveState(state) {
  state.updatedAt = new Date().toISOString();
  const target = stateFile();
  const temp = `${target}.${process.pid}.tmp`;
  await fs.mkdir(dataDir(), { recursive: true });
  await fs.writeFile(temp, JSON.stringify(state));
  await fs.rename(temp, target);
}
// Fold per-browser snapshots from the previous layout into the shared state.
async function readLegacySnapshots() {
  let names = [];
  try { names = await fs.readdir(dataDir()); } catch { return []; }
  const snapshots = [];
  for (const name of names) {
    if (!name.endsWith('.json') || name === 'state.json') continue;
    try {
      const snapshot = JSON.parse(await fs.readFile(path.join(dataDir(), name), 'utf8'));
      if (snapshot && Array.isArray(snapshot.entries)) snapshots.push(snapshot);
    } catch { /* ignore a foreign or half-written file */ }
  }
  return snapshots.sort((a, b) => String(a.savedAt).localeCompare(String(b.savedAt)));
}
async function loadState() {
  try {
    const raw = JSON.parse(await fs.readFile(stateFile(), 'utf8'));
    if (raw && Array.isArray(raw.entries)) return raw;
  } catch { /* first run, or no state yet */ }
  let entries = [];
  for (const snapshot of (await readLegacySnapshots()).reverse()) {
    try { entries = R.mergeEntries(entries, snapshot.entries).entries; } catch { /* skip an oversized snapshot */ }
  }
  const state = { version: 1, updatedAt: new Date().toISOString(), entries };
  if (entries.length) await saveState(state);
  return state;
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
async function handleSession(req, res) {
  if (req.method === 'GET' || req.method === 'HEAD') { json(res, 200, sessionOf(await loadState())); return; }
  if (req.method !== 'POST') { json(res, 405, { error: 'Method not allowed.' }); return; }
  let parsed;
  try { parsed = R.parseFile(await readBody(req)); }
  catch (error) { json(res, 400, { error: error.message }); return; }
  if (!parsed.session) { json(res, 400, { error: 'Send a review session file.' }); return; }
  const state = await loadState();
  // Additive: new examples join the shared workspace, existing decisions stay.
  const merged = R.mergeEntries(state.entries, parsed.entries);
  state.entries = merged.entries;
  try { await saveState(state); } catch { json(res, 500, { error: 'Could not save the review session.' }); return; }
  json(res, 200, { added: merged.added, total: state.entries.length, exports: await materialize(state) });
}
// One approve/deny/clear applied to the shared entry for that example.
async function handleDecision(req, res) {
  if (req.method !== 'POST') { json(res, 405, { error: 'Method not allowed.' }); return; }
  let body;
  try { body = JSON.parse(await readBody(req)); }
  catch { json(res, 400, { error: 'Send JSON.' }); return; }
  const decision = body ? body.decision : undefined;
  if (!body || typeof body.key !== 'string' || !body.key || ![null, 'approve', 'deny'].includes(decision)) {
    json(res, 400, { error: 'Send a key and a decision of approve, deny or null.' });
    return;
  }
  const state = await loadState();
  let index = state.entries.findIndex(entry => R.stable(entry.example) === body.key);
  if (index < 0) {
    // A client may review an example the server has not seen yet (a file
    // imported locally); accept it rather than losing the decision.
    let example;
    try { example = R.validateExample(body.example, state.entries.length); }
    catch { json(res, 404, { error: 'That example is not in the shared workspace.' }); return; }
    state.entries.push({ example, decision: null, reason: '', reviewedAt: null });
    index = state.entries.length - 1;
  }
  state.entries[index] = {
    ...state.entries[index],
    decision,
    reason: decision ? String(body.reason || '').trim() : '',
    reviewedAt: decision ? new Date().toISOString() : null
  };
  try { await saveState(state); } catch { json(res, 500, { error: 'Could not save that decision.' }); return; }
  json(res, 200, { decision, counts: await materialize(state) });
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
  try { body = build((await loadState()).entries); }
  catch { json(res, 500, { error: 'Could not build the export.' }); return; }
  const buffer = Buffer.from(body, 'utf8');
  res.writeHead(200, {
    'Content-Type': `${type}; charset=utf-8`,
    'Content-Length': buffer.length,
    'Content-Disposition': `attachment; filename="${filename}"`
  });
  res.end(req.method === 'HEAD' ? undefined : buffer);
}
// Every save rewrites the dataset files so what sits on disk is always current.
// EXPORT_DIR lets them land inside the repository, where git can carry them.
async function materialize(state) {
  const entries = state ? state.entries : (await loadState()).entries;
  const dir = exportDir();
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
    if (route === '/api/session') { await handleSession(req, res); return; }
    if (route === '/api/decision') { await handleDecision(req, res); return; }
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
    console.log(`Dataset: ${datasetDir() || examplesFile()}`);
    console.log(`Shared state: ${stateFile()}`);
    console.log(`Generated files: ${exportDir()}`);
    if (host === '0.0.0.0') {
      for (const list of Object.values(os.networkInterfaces())) for (const net of list || []) if (net.family === 'IPv4' && !net.internal) console.log(`Same Wi-Fi / LAN: http://${net.address}:${actualPort}`);
    }
  });
}
