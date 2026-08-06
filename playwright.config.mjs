import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/browser',
  timeout: 30000,
  workers: 1,
  use: {
    baseURL: 'http://127.0.0.1:8010',
    channel: 'msedge',
    serviceWorkers: 'block',
    trace: 'retain-on-failure'
  },
  webServer: {
    command: 'python -m uvicorn kaoyan_ai.api:app --host 127.0.0.1 --port 8010',
    url: 'http://127.0.0.1:8010/health',
    reuseExistingServer: true,
    timeout: 120000
  },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1440, height: 900 } } },
    { name: 'tablet', use: { viewport: { width: 900, height: 1100 } } },
    { name: 'mobile', use: { viewport: { width: 390, height: 844 } } }
  ]
});
