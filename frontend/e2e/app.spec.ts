import { test, expect } from '@playwright/test';

test('actual application: watch controls, language persistence, real NOAA replay and responsive map', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => {
    if (!localStorage.getItem('tlaloc.e2e.seeded')) {
      localStorage.setItem('i18nextLng', 'en');
      localStorage.setItem('tlaloc.location', JSON.stringify({ lat: 0, lon: 0, radius_km: 50, threshold: .2 }));
      localStorage.setItem('tlaloc.e2e.seeded', 'yes');
    }
  });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Weather in motion.' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Insufficient coverage', exact: true })).toBeVisible();
  await expect(page.locator('.target-marker')).toHaveCount(1);
  await expect(page.getByLabel('Radius', { exact: true })).toHaveValue('50');
  await page.getByLabel('Radius', { exact: true }).fill('75');
  await expect.poll(() => page.evaluate(() => JSON.parse(localStorage.getItem('tlaloc.location')!).radius_km)).toBe(75);
  await page.getByLabel('Latitude', { exact: true }).fill('0.2');
  await page.getByLabel('Latitude', { exact: true }).press('Enter');
  await expect.poll(() => page.evaluate(() => JSON.parse(localStorage.getItem('tlaloc.location')!).lat)).toBe(.2);
  const marker = await page.locator('.target-marker').boundingBox();
  expect(marker).not.toBeNull();
  await page.mouse.move(marker!.x + marker!.width/2, marker!.y + marker!.height/2);
  await page.mouse.down();
  await page.mouse.move(marker!.x + marker!.width/2 + 35, marker!.y + marker!.height/2, { steps: 8 });
  await page.mouse.up();
  await expect.poll(() => page.evaluate(() => JSON.parse(localStorage.getItem('tlaloc.location')!).lon)).not.toBe(0);
  await page.getByRole('button', { name: 'Change language' }).click();
  await expect(page.locator('html')).toHaveAttribute('lang', 'es');
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('lang', 'es');
  await expect(page.getByLabel('Radio', { exact: true })).toHaveValue('75');
  await page.getByRole('button', { name: 'Cambiar idioma' }).click();
  await page.getByRole('button', { name: 'Historical replay', exact: true }).click();
  const responsePromise = page.waitForResponse(response => response.url().endsWith('/api/replay') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Load real example', exact: true }).click();
  const response = await responsePromise;
  expect(response.status()).toBe(200);
  const replay = await response.json();
  expect(replay.frame_count).toBe(11);
  expect(replay.steps[0].frame.source).toContain('noaa-mrms-pds.s3.amazonaws.com');
  expect(replay.metrics.target_data_availability).toBe(1);
  await expect(page.getByRole('heading', { name: 'Observations available', exact: true })).toBeVisible();
  await expect(page.locator('.leaflet-image-layer')).toHaveCount(1);
  await expect.poll(() => page.locator('.leaflet-tile-pane img').evaluateAll(elements => elements.filter(element => (element as HTMLImageElement).src.startsWith('https://tile.openstreetmap.org/') && (element as HTMLImageElement).complete && (element as HTMLImageElement).naturalWidth > 0).length)).toBeGreaterThan(0);
  await page.getByLabel('Observation time', { exact: true }).fill('10');
  const displayedLayer = replay.steps[10].frame.layers.rate;
  await expect(page.locator('.timeline-track strong')).toContainText(new Date(displayedLayer.time).toISOString().slice(11, 16));
  await expect(page.locator('.threat')).toHaveCount(replay.steps[10].predictions.length);
  await page.screenshot({ path: '../.cache/browser/desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator('.radar-map')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: '../.cache/browser/mobile.png', fullPage: true });
  expect(errors).toEqual([]);
});
