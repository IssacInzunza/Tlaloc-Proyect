import { test, expect, type Page } from '@playwright/test';

const id = 'fixture_subscription_123456';
const location = { lat: 32.6, lon: -115.4, radius_km: 50, threshold: .2 };
async function fixtures(page: Page, permission: 'granted' | 'denied' = 'granted') {
  await page.addInitScript(permission => {
    localStorage.setItem('i18nextLng', 'en');
    (window as any).pushPermissionCalls = 0;
    const notification = { permission: 'default', requestPermission: async () => { (window as any).pushPermissionCalls++; notification.permission = permission; return permission; } };
    Object.defineProperty(window, 'Notification', { value: notification, configurable: true });
    Object.defineProperty(window, 'PushManager', { value: function () {}, configurable: true });
    const subscription = { toJSON: () => ({ endpoint: 'https://push.example.invalid/fixture', keys: { p256dh: 'fixture', auth: 'fixture' } }), unsubscribe: async () => true };
    const registration = { pushManager: { getSubscription: async () => null, subscribe: async () => subscription } };
    Object.defineProperty(navigator, 'serviceWorker', { configurable: true, value: { register: async () => registration, ready: Promise.resolve(registration), getRegistration: async () => registration } });
  }, permission);
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname;
    const json = path.endsWith('/config') ? { enabled: true, public_key: 'BAECAwQ' }
      : path.endsWith('/status') ? { enabled: true, last_checked: null, last_sent: null, last_error: null }
      : path.startsWith('/api/notifications') ? { id, enabled: true }
      : path === '/api/analysis' ? { location, coverage: { status: 'provider_unavailable', valid_fraction: 0, target_valid: false, age_minutes: null, quality: 'product_mask_only' }, frames: [], predictions: [], observation_time: null, processing_seconds: 0 }
      : [];
    return route.fulfill({ json });
  });
}
async function openSettings(page: Page) {
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: 'Settings', exact: true }).click();
}

test('push permission is a user gesture; enabling, updating, testing and disabling use real client contracts with mocked transport', async ({ page }) => {
  await fixtures(page);
  await openSettings(page);
  expect(await page.evaluate(() => (window as any).pushPermissionCalls)).toBe(0);
  const component = page.getByTestId('notification-settings');
  await component.getByRole('button', { name: 'Enable rain notifications', exact: true }).click();
  await expect(component).toContainText('Background watch enabled.');
  expect(await page.evaluate(() => localStorage.getItem('tlaloc.pushId'))).toBe(id);
  const updated = page.waitForRequest(request => request.url().endsWith(`/notifications/${id}/update`) && request.postDataJSON().location.threshold === .5);
  await page.locator('input[type="number"][max="10"]').fill('0.5'); await updated;
  const testRequest = page.waitForRequest(request => request.url().endsWith(`/notifications/${id}/test`));
  await component.getByRole('button', { name: 'Send test notification', exact: true }).click(); await testRequest;
  await expect(component).toContainText('Test accepted by the push service.');
  await component.getByRole('button', { name: 'Disable rain notifications', exact: true }).click();
  await expect(component).toContainText('Background notifications disabled.');
  expect(await page.evaluate(() => localStorage.getItem('tlaloc.pushId'))).toBeNull();
});

test('blocked permission is distinct from subscription transport failure and does not subscribe', async ({ page }) => {
  await fixtures(page, 'denied');
  let subscribes = 0; page.on('request', request => { if (request.url().endsWith('/notifications/subscribe')) subscribes++; });
  await openSettings(page);
  await page.getByRole('button', { name: 'Enable rain notifications', exact: true }).click();
  await expect(page.getByTestId('notification-settings').getByRole('alert')).toContainText('Notifications are blocked');
  expect(subscribes).toBe(0);
});

test('saved watch does not request permission on reload and replay never updates its location', async ({ page }) => {
  await fixtures(page);
  await page.addInitScript(id => localStorage.setItem('tlaloc.pushId', id), id);
  await openSettings(page);
  await expect(page.getByTestId('notification-settings')).toContainText('Background watch enabled.');
  await page.getByRole('button', { name: 'Historical replay', exact: true }).click();
  let updates = 0; page.on('request', request => { if (request.url().endsWith(`/notifications/${id}/update`)) updates++; });
  await page.getByLabel('Latitude', { exact: true }).fill('30'); await page.getByLabel('Latitude', { exact: true }).press('Enter');
  await page.waitForTimeout(800);
  expect(updates).toBe(0);
  expect(await page.evaluate(() => (window as any).pushPermissionCalls)).toBe(0);
});

test('root service worker really registers locally without asking notification permission', async ({ page }) => {
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  const result = await page.evaluate(async () => {
    const before = Notification.permission;
    await navigator.serviceWorker.register('/sw.js', { scope: '/' });
    const registration = await navigator.serviceWorker.ready;
    return { scope: registration.scope, active: !!registration.active, permissionUnchanged: Notification.permission === before };
  });
  expect(result).toEqual({ scope: 'http://127.0.0.1:8000/', active: true, permissionUnchanged: true });
});
