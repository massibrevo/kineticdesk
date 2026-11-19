import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  workers: 1,
  use: {
    baseURL: process.env.KINETICDESK_TEST_URL ?? 'http://127.0.0.1:5174',
    launchOptions: { executablePath: process.env.KINETICDESK_CHROME },
  },
})
