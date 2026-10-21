import { test, expect } from '@playwright/test';

for (const [status, detail, text] of [
  [403, 'monitor_same_origin_required', 'The server rejected this page origin.'],
  [409, 'monitor_limit', 'Eight locations are already saved.'],
  [422, 'invalid', 'The location or name is invalid.'],
] as const) {
  test(`monitor save explains HTTP ${status} instead of blaming the location limit`, async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem('i18nextLng', 'en'));
    await page.route('https://tile.openstreetmap.org/**', route => route.abort());
    await page.route('**/api/**', route => route.fulfill({ json: [] }));
    await page.route('**/api/analysis?**', route => route.fulfill({ json: { location: { lat: 32, lon: -115, radius_km: 50, threshold: .2 }, coverage: { status: 'available' }, frames: [], predictions: [], observation_time: null, processing_seconds: 0 } }));
    await page.route('**/api/monitors', route => route.request().method() === 'GET'
      ? route.fulfill({ json: [] }) : route.fulfill({ status, json: { detail } }));
    await page.goto('/');
    const panel = page.getByRole('region', { name: 'Monitored locations' });
    await panel.getByRole('textbox', { name: 'Location name' }).fill('Casa');
    await panel.getByRole('button', { name: 'Save and monitor current location' }).click();
    await expect(panel.getByRole('alert')).toContainText(text);
    if (status !== 409) await expect(panel.getByRole('alert')).not.toContainText('Eight locations');
    await expect(panel.getByRole('textbox')).toHaveValue('Casa');
  });
}
