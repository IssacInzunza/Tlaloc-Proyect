import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './e2e',
  timeout: 90000,
  expect: { timeout: 30000 },
  workers: 1,
  use: { baseURL: 'http://127.0.0.1:8000', channel: process.env.TLALOC_BROWSER_CHANNEL || (process.platform === 'win32' ? 'msedge' : undefined), headless: true, viewport: { width: 1440, height: 1050 } },
  reporter: 'list',
});
