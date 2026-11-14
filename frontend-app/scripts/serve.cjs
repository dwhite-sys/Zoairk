const http = require('node:http');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const root = path.resolve(__dirname, '..');
const files = new Map([
  ['/', ['index.html', 'text/html']], ['/index.html', ['index.html', 'text/html']],
  ['/style.css', ['style.css', 'text/css']], ['/app.js', ['app.js', 'application/javascript']],
  ['/world.js', ['world.js', 'application/javascript']]
]);
function createServer() {
  return http.createServer(async (request, response) => {
    response.setHeader('Cache-Control', 'no-store');
    response.setHeader('X-Content-Type-Options', 'nosniff');
    if (!['GET', 'HEAD'].includes(request.method)) { response.writeHead(405, { Allow: 'GET, HEAD' }); response.end(); return; }
    const asset = files.get(request.url.split('?')[0]);
    if (!asset) { response.writeHead(404); response.end('Not found'); return; }
    try {
      const bytes = await fs.readFile(path.join(root, asset[0]));
      response.writeHead(200, { 'Content-Type': asset[1] + '; charset=utf-8', 'Content-Length': bytes.length });
      response.end(request.method === 'HEAD' ? undefined : bytes);
    } catch { response.writeHead(500); response.end('Could not read frontend file'); }
  });
}
module.exports = { createServer };
if (require.main === module) {
  const hostIndex = process.argv.indexOf('--host');
  const host = hostIndex < 0 ? '127.0.0.1' : process.argv[hostIndex + 1];
  const port = Number(process.env.PORT || 3001);
  if (!host || !Number.isInteger(port) || port < 0 || port > 65535) throw new Error('Use a valid host and PORT.');
  const server = createServer();
  server.on('error', error => { console.error(error.message); process.exitCode = 1; });
  server.listen(port, host, () => {
    console.log('Zoairk frontend: http://localhost:' + server.address().port);
    if (host === '0.0.0.0') for (const list of Object.values(os.networkInterfaces())) for (const net of list || []) if (net.family === 'IPv4' && !net.internal) console.log('Same-network URL: http://' + net.address + ':' + server.address().port);
  });
}
