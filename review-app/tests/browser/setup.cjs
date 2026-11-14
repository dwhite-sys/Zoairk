const { createServer } = require('../../scripts/serve.cjs');
module.exports = async function () {
  const server = createServer();
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(3100, '127.0.0.1', resolve); });
  return async () => { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); };
};
