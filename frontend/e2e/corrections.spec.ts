import { test, expect } from '@playwright/test';

const saved = { lat: 32.61, lon: -115.44, radius_km: 75, threshold: .3 };
const historical = { lat: 27, lon: -82, radius_km: 50, threshold: .2 };
const time = new Date().toISOString();
const coverage = { status: 'available', valid_fraction: 1, target_valid: true, age_minutes: 0, quality: 'product_mask_only' };
const png = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLbtAAAAABJRU5ErkJggg==';
const layer = { image: png, bounds: [[31,-116],[33,-114]], time, source: 'https://example.org/real-observation', valid_fraction: 1, max_value: 20, echo_pixels: 4 };
const frame = { ...layer, coverage, layers: { rate: { ...layer, unit: 'mm/h', echo_pixels: 0 }, reflectivity: { ...layer, unit: 'dBZ' } } };

test.beforeEach(async ({ page }) => {
  await page.addInitScript(location => {
    localStorage.setItem('i18nextLng', 'en');
    if (!localStorage.getItem('tlaloc.location')) localStorage.setItem('tlaloc.location', JSON.stringify(location));
  }, saved);
  await page.route('https://tile.openstreetmap.org/**', route => route.fulfill({ contentType: 'image/png', body: Buffer.from(png.split(',')[1], 'base64') }));
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    const body = path === '/api/analysis' ? { location: saved, coverage, frames: [frame], predictions: [], observation_time: time, processing_seconds: 0 }
      : path === '/api/sample' ? { location: historical, frames: [{ time: '2026-01-01T00:00:00Z' }, { time: '2026-01-01T00:02:00Z' }] }
      : path === '/api/replay' ? { run_id: 'fixture', location: historical, start: '2026-01-01T00:00:00Z', end: '2026-01-01T00:02:00Z', metrics: {}, steps: [{ time, coverage, frame, predictions: [] }] }
      : [];
    await route.fulfill({ json: body });
  });
});

test('sample replay and temporary edits preserve browser watch; returning live and reload restore it', async ({ page }) => {
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: 'Historical replay', exact: true }).click();
  await page.getByRole('button', { name: 'Load real example', exact: true }).click();
  await expect(page.getByLabel('Latitude', { exact: true })).toHaveValue('27');
  await expect.poll(() => page.evaluate(() => JSON.parse(localStorage.getItem('tlaloc.location')!))).toEqual(saved);
  await page.getByLabel('Radius', { exact: true }).fill('90');
  await expect.poll(() => page.evaluate(() => JSON.parse(localStorage.getItem('tlaloc.location')!))).toEqual(saved);
  await page.getByRole('button', { name: 'Live monitor', exact: true }).click();
  await expect(page.getByLabel('Latitude', { exact: true })).toHaveValue(String(saved.lat));
  await expect(page.getByLabel('Radius', { exact: true })).toHaveValue('75');
  await page.getByRole('button', { name: 'Pause updates', exact: true }).click();
  await page.getByLabel('Latitude', { exact: true }).fill('32.67');
  await page.getByLabel('Latitude', { exact: true }).press('Enter');
  await expect.poll(() => page.evaluate(() => JSON.parse(localStorage.getItem('tlaloc.location')!).lat)).toBe(32.67);
  await page.reload();
  await expect(page.getByLabel('Latitude', { exact: true })).toHaveValue('32.67');
  await expect(page.getByLabel('Radius', { exact: true })).toHaveValue('75');
});

test('Photon is enabled even after an older disabled preference, with debounce and keyboard search', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('tlaloc.addressConsent', 'false'));
  const searches: URL[] = [];
  await page.route('**/api/search?**', async route => {
    searches.push(new URL(route.request().url()));
    await route.fulfill({ json: [{ name: 'Example street, Example city', lat: 32.7, lon: -115.5 }] });
  });
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  const search = page.getByRole('combobox', { name: 'Search street, neighborhood or city' });
  await search.fill('example street');
  await expect(page.getByRole('listbox').getByRole('option')).toContainText('Example street');
  expect(searches).toHaveLength(1);
  expect(searches[0].searchParams.get('suggest')).toBe('true');
  expect(searches[0].searchParams.get('external')).toBe('true');
  await search.press('ArrowDown'); await search.press('Enter');
  await expect(page.getByLabel('Latitude', { exact: true })).toHaveValue('32.7');
  await expect(page.getByRole('listbox')).toHaveCount(0);
  await search.fill('another street'); await search.press('Enter');
  await expect.poll(() => searches.at(-1)?.searchParams.get('suggest')).toBe('false');
  await expect(page.getByRole('listbox').getByRole('option')).toBeVisible();
  await search.press('Escape');
  await expect(page.getByRole('listbox')).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole('checkbox', { name: /Enable external search/ })).toHaveCount(0);
  await expect(page.getByLabel('Latitude', { exact: true })).toHaveValue('32.7');
});

test('precipitation is the initial layer; a chosen reflectivity layer is restored locally on reload', async ({ page }) => {
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await expect(page.getByLabel('Radar layer', { exact: true })).toHaveValue('rate');
  await expect(page.locator('.legend')).toContainText('mm/h');
  await page.getByLabel('Radar layer', { exact: true }).selectOption('reflectivity');
  await expect.poll(() => page.evaluate(() => JSON.parse(localStorage.getItem('tlaloc.radarLayer')!))).toBe('reflectivity');
  await page.reload();
  await expect(page.getByLabel('Radar layer', { exact: true })).toHaveValue('reflectivity');
  await expect(page.locator('.leaflet-image-layer')).toHaveCount(1);
  await expect(page.locator('.legend')).toContainText('dBZ');
  await expect(page.locator('.radar-explanation')).toContainText('do not confirm surface rainfall');
  await expect(page.locator('.layer-data')).toContainText('100%');
  await page.screenshot({ path: '../.cache/browser/corrections-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: '../.cache/browser/corrections-mobile.png', fullPage: true });
  await page.getByLabel('Radar layer', { exact: true }).selectOption('rate');
  await expect(page.locator('.legend')).toContainText('mm/h');
  await expect(page.locator('.map-message')).toContainText('No detectable estimated precipitation');
});

test('a saved radar selection remains selected when a frame is missing that product', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('tlaloc.radarLayer', JSON.stringify('reflectivity')));
  await page.route('**/api/analysis?**', route => route.fulfill({ json: { location: saved, coverage, frames: [{ ...frame, layers: { rate: frame.layers.rate } }, frame], predictions: [], observation_time: time, processing_seconds: 0 } }));
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await expect(page.getByLabel('Radar layer', { exact: true })).toHaveValue('reflectivity');
  await page.getByLabel('Observation time', { exact: true }).fill('0');
  await expect(page.getByLabel('Radar layer', { exact: true })).toHaveValue('reflectivity');
  await expect(page.locator('.leaflet-image-layer')).toHaveCount(0);
  await expect(page.locator('.map-message')).toContainText('selected layer is unavailable');
  await page.getByLabel('Observation time', { exact: true }).fill('1');
  await expect(page.locator('.leaflet-image-layer')).toHaveCount(1);
});

test('rate-limited suggestions retry the latest query and cancel retries on edits or close', async ({ page }) => {
  const calls: Record<string, number> = {};
  await page.route('**/api/search?**', async route => {
    const q = new URL(route.request().url()).searchParams.get('q')!;
    calls[q] = (calls[q] ?? 0) + 1;
    if (q === 'latest street' && calls[q] > 1) await route.fulfill({ json: [{ name: 'First result', lat: 32.7, lon: -115.5 }, { name: 'Last result', lat: 32.8, lon: -115.6 }] });
    else await route.fulfill({ status: 429, json: { detail: 'search_rate_limit' } });
  });
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  const search = page.getByRole('combobox', { name: 'Search street, neighborhood or city' });
  await search.fill('obsolete street');
  await expect.poll(() => calls['obsolete street']).toBe(1);
  await search.fill('latest street');
  await expect(page.getByRole('listbox').getByRole('option')).toHaveCount(2);
  expect(calls['obsolete street']).toBe(1); expect(calls['latest street']).toBe(2);
  await search.press('ArrowUp');
  await expect(search).toHaveAttribute('aria-activedescendant', 'address-option-1');
  await search.press('Enter');
  await expect(page.getByLabel('Latitude', { exact: true })).toHaveValue('32.8');
  await search.fill('closed street');
  await expect.poll(() => calls['closed street']).toBe(1);
  await search.press('Escape');
  await page.waitForTimeout(1300);
  expect(calls['closed street']).toBe(1); await expect(page.getByRole('listbox')).toHaveCount(0);
});

test('suggestion retries stop after three retries when the provider stays rate-limited', async ({ page }) => {
  let calls = 0;
  await page.route('**/api/search?**', async route => { calls++; await route.fulfill({ status: 429, json: { detail: 'search_rate_limit' } }); });
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await page.getByRole('combobox', { name: 'Search street, neighborhood or city' }).fill('bounded retry street');
  await expect(page.getByRole('status')).toContainText(/wait a moment/i, { timeout: 15000 });
  expect(calls).toBe(4);
  await page.waitForTimeout(1300);
  expect(calls).toBe(4);
});

