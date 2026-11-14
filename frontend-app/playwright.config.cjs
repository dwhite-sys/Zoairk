const { defineConfig } = require('@playwright/test');
module.exports = defineConfig({
  testDir: './tests/browser', workers: 1, timeout: 30000,
  globalSetup: require.resolve('./tests/browser/setup.cjs'),
  use: { baseURL: 'http://127.0.0.1:3101', trace: 'retain-on-failure' },
  projects: [
    { name: 'desktop', use: { browserName: 'chromium', channel: 'msedge', viewport: { width: 1440, height: 1000 } } },
    { name: 'mobile', use: { browserName: 'chromium', channel: 'msedge', viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } }
  ]
});
