import { test, expect, type Page } from '@playwright/test';

const location = { lat: 32.6, lon: -115.4, radius_km: 50, threshold: .2 };
const coverage = { status: 'available', valid_fraction: 1, target_valid: true, age_minutes: 1, quality: 'radar_quality_good' };
const image = (color: string) => `data:image/svg+xml,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4"><rect width="4" height="4" fill="${color}"/></svg>`)}`;
function analysis(time: string, color = 'green', stationary = false) {
  return { location, coverage, observation_time: time, processing_seconds: 0,
    frames: [{ time, image: image(color), bounds: [[32, -116], [33, -115]], source: 'fixture', coverage }],
    predictions: stationary ? [{ id: 'stationary', level: 'informational', intensity: 'moderate', peak_rate: 9, area_km2: 100, distance_km: 26, lat: 32.4, lon: -115.2, direction_deg: null, speed_kmh: 0, arrival_minutes: null, arrival_status: 'stationary', confidence: 'medium', event: 'observed', observation_time: time, data_quality: 'radar_quality_good', vector_end: [32.4, -115.2], polygon: [] }] : [] };
}
async function setup(page: Page) {
  await page.addInitScript(location => { localStorage.setItem('i18nextLng', 'en'); localStorage.setItem('tlaloc.location', JSON.stringify(location)); }, location);
  await page.route('https://tile.openstreetmap.org/**', route => route.abort());
  await page.route('**/api/**', route => route.fulfill({ json: [] }));
}

test('new radar images arrive without F5 across multiple polls; stationary regions have no arrow', async ({ page }) => {
  await setup(page); await page.clock.install();
  let count = 0;
  await page.route('**/api/analysis?**', route => route.fulfill({ json: analysis(new Date(Date.now()).toISOString(), ['green', 'red', 'blue'][Math.min(count++, 2)], true) }));
  await page.goto('/');
  await expect(page.locator('.leaflet-image-layer')).toHaveAttribute('src', image('green'));
  await expect(page.locator('.arrival')).toContainText('No detectable movement');
  await expect(page.locator('.motion-arrow')).toHaveCount(0);
  await expect(page.locator('.threat h3 svg')).toHaveCount(0);
  await page.clock.fastForward(61000);
  await expect(page.locator('.leaflet-image-layer')).toHaveAttribute('src', image('red'));
  await page.clock.fastForward(61000);
  await expect(page.locator('.leaflet-image-layer')).toHaveAttribute('src', image('blue'));
  await expect(page.locator('.freshness')).toContainText('Last completed check');
  await page.screenshot({ path: '../.cache/browser/live-fixes-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: '../.cache/browser/live-fixes-mobile.png', fullPage: true });
});

test('a download lasting over a minute completes instead of being cancelled by polling', async ({ page }) => {
  await setup(page); await page.clock.install();
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  let count = 0;
  await page.route('**/api/analysis?**', async route => { count++; await pending; await route.fulfill({ json: analysis(new Date().toISOString()) }); });
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await expect.poll(() => count).toBe(1);
  await page.clock.fastForward(125000);
  expect(count).toBe(1);
  release();
  await expect(page.locator('.leaflet-image-layer')).toHaveAttribute('src', image('green'));
});

test('disconnect preserves the last image, reconnect refreshes, stale data is labeled', async ({ page, context }) => {
  await setup(page);
  let count = 0;
  await page.route('**/api/analysis?**', route => route.fulfill({ json: analysis(new Date(Date.now() - 11 * 60000).toISOString(), count++ ? 'red' : 'green') }));
  await page.goto('/');
  await expect(page.locator('.map-status')).toContainText('Stale observations');
  await context.setOffline(true);
  await expect(page.locator('.map-status')).toContainText('Offline');
  await expect(page.locator('.leaflet-image-layer')).toHaveAttribute('src', image('green'));
  await context.setOffline(false);
  await expect(page.locator('.leaflet-image-layer')).toHaveAttribute('src', image('red'));
});

test('focus refreshes immediately and a failed refresh preserves the last image', async ({ page }) => {
  await setup(page); let count = 0;
  await page.route('**/api/analysis?**', route => ++count === 2 ? route.abort('failed') : route.fulfill({ json: analysis(new Date().toISOString(), count > 2 ? 'blue' : 'green') }));
  await page.goto('/');
  await expect(page.locator('.leaflet-image-layer')).toHaveAttribute('src', image('green'));
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await expect(page.locator('.map-status')).toContainText('Update failed');
  await expect(page.locator('.leaflet-image-layer')).toHaveAttribute('src', image('green'));
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await expect(page.locator('.leaflet-image-layer')).toHaveAttribute('src', image('blue'));
});

test('save, disable and remove a monitor without requesting notification permission', async ({ page }) => {
  await setup(page);
  let records: any[] = [];
  await page.route('**/api/monitors**', async route => {
    const request = route.request();
    if (request.method() === 'POST') records = [{ ...request.postDataJSON(), id: 'saved-location' }];
    if (request.method() === 'DELETE') records = [];
    await route.fulfill({ json: request.method() === 'GET' ? records : {} });
  });
  await page.route('**/api/analysis?**', route => route.fulfill({ json: analysis(new Date().toISOString()) }));
  let pushCalls = 0; page.on('request', request => { if (request.url().includes('/api/notifications/subscribe')) pushCalls++; });
  await page.goto('/');
  const panel = page.getByRole('region', { name: 'Monitored locations' });
  await panel.getByRole('textbox', { name: 'Location name' }).fill('Mexicali');
  await panel.getByRole('button', { name: 'Save and monitor current location' }).click();
  await expect(panel.getByRole('button', { name: 'Mexicali', exact: true })).toBeVisible();
  await panel.getByRole('checkbox', { name: 'Monitor', exact: true }).uncheck();
  await expect(panel.getByRole('checkbox')).not.toBeChecked();
  await panel.getByRole('button', { name: 'Remove Mexicali' }).click();
  await expect(panel.getByRole('checkbox')).toHaveCount(0);
  expect(pushCalls).toBe(0);
});
