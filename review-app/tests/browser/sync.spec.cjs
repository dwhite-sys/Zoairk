const { test, expect } = require('@playwright/test');

test('decisions reach the server and a fresh browser restores them', async ({ page, browser }) => {
  await page.goto('/');
  await page.getByRole('button', { name: /sample examples/i }).click();
  await expect(page.locator('#pending-count')).toHaveText('10');

  await page.getByRole('button', { name: /Approve example/i }).click();
  await expect(page.locator('#approved-count')).toHaveText('1');
  // The save indicator only says this once a POST has succeeded.
  await expect(page.locator('#save-status')).toHaveText(/on the server/i);

  const clientId = await page.evaluate(async () => {
    const db = await new Promise((resolve, reject) => {
      const request = indexedDB.open('zoairk-example-review', 1);
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    return await new Promise((resolve, reject) => {
      const request = db.transaction('workspace').objectStore('workspace').get('client');
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  });
  expect(clientId).toBeTruthy();

  // Ask the server as somebody else: the approval has to be there.
  const shared = await (await page.request.get('/api/session?client=someoneelse123456')).json();
  expect(shared.entries.filter(entry => entry.decision === 'approve').length).toBeGreaterThan(0);

  // A brand new browser profile has no IndexedDB; it must pull the decision down.
  const context = await browser.newContext();
  const fresh = await context.newPage();
  await fresh.goto('/');
  await expect(fresh.locator('#approved-count')).toHaveText('1');
  await expect(fresh.locator('#total-count')).toHaveText('10');
  await context.close();
});
