const { createServer } = require('../../scripts/serve.cjs');
const { createBackend } = require('../fixtures/backend.cjs');
module.exports = async function () {
  const frontend = createServer();
  await new Promise((resolve, reject) => { frontend.once('error', reject); frontend.listen(3101, '127.0.0.1', resolve); });
  const backend = await createBackend(8083);
  return async () => { await backend.close(); frontend.closeAllConnections(); await new Promise(resolve => frontend.close(resolve)); };
};
