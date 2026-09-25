import { defineConfig, devices } from "@playwright/test";

/**
 * Browser E2E for the SecureHealth golden path (Implementation Plan §24/§25).
 * Both servers auto-start against a dedicated e2e.db; local runs reuse any
 * already-running instance.
 */
export default defineConfig({
  testDir: "./tests",
  timeout: 300_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:3000",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "python -m uvicorn app.main:app --port 8000",
      url: "http://localhost:8000/api/v1/health",
      timeout: 120_000,
      reuseExistingServer: !process.env.CI,
      cwd: "../backend",
      env: {
        SECUREHEALTH_ENV: "development",
        SECUREHEALTH_DATABASE_URL: "sqlite:///./e2e.db",
        SECUREHEALTH_SECURITY_SCAN_MODE: "stub",
        // E2E drives many auth calls from one IP inside 60s windows; the
        // 10/min production limit itself is covered by the pytest suite.
        SECUREHEALTH_RATE_LIMIT_AUTH: "100",
        SECUREHEALTH_RATE_LIMIT_GENERAL: "1000",
      },
    },
    {
      command: "npm run dev",
      url: "http://localhost:3000",
      timeout: 240_000,
      reuseExistingServer: !process.env.CI,
      cwd: "../frontend",
    },
  ],
});
