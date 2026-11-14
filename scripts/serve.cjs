'use strict';
const http = require('node:http');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const root = path.resolve(__dirname, '..');
const files = new Map([
  ['/', ['index.html', 'text/html; charset=utf-8']],
  ['/index.html', ['index.html', 'text/html; charset=utf-8']],
  ['/styles.css', ['styles.css', 'text/css; charset=utf-8']],
  ['/review.js', ['review.js', 'application/javascript; charset=utf-8']],
  ['/app.js', ['app.js', 'application/javascript; charset=utf-8']],
  ['/examples.json', ['examples.json', 'application/json; charset=utf-8']]
]);
function createServer() {
  return http.createServer(async (req, res) => {
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('Referrer-Policy', 'no-referrer');
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'");
    if (!['GET', 'HEAD'].includes(req.method)) { res.writeHead(405, { Allow: 'GET, HEAD' }); res.end('Method not allowed'); return; }
    const route = req.url.split('?')[0];
    const file = files.get(route);
    if (!file) { res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' }); res.end('Not found'); return; }
    try {
      const content = await fs.readFile(path.join(root, file[0]));
      res.writeHead(200, { 'Content-Type': file[1], 'Content-Length': content.length });
      res.end(req.method === 'HEAD' ? undefined : content);
    } catch { res.writeHead(500); res.end('Could not read application asset.'); }
  });
}
module.exports = { createServer };
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
    console.log(`Zoairk review: http://localhost:${actualPort}`);
    if (host === '0.0.0.0') {
      for (const list of Object.values(os.networkInterfaces())) for (const net of list || []) if (net.family === 'IPv4' && !net.internal) console.log(`Same Wi-Fi / LAN: http://${net.address}:${actualPort}`);
      console.log('Only static app assets are served. Reviews stay in each browser.');
    }
  });
}
