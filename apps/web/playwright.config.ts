import { defineConfig } from "@playwright/test";

const apiPort = process.env.E2E_API_PORT ?? "8001";
const webPort = process.env.E2E_WEB_PORT ?? "4173";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  timeout: 30_000,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI
    ? [["github"], ["html", { open: "never" }]]
    : [["line"], ["html", { open: "never" }]],
  use: {
    baseURL: `http://127.0.0.1:${webPort}`,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: [
    {
      command: "python scripts/run_e2e_server.py",
      cwd: "../api",
      url: `http://127.0.0.1:${apiPort}/api/auth/session/`,
      reuseExistingServer: false,
      stdout: "pipe",
      stderr: "pipe",
      timeout: 120_000,
      env: {
        ...process.env,
        E2E_API_PORT: apiPort,
        E2E_WEB_PORT: webPort,
        DJANGO_ALLOWED_HOSTS: "127.0.0.1,localhost,testserver",
      },
    },
    {
      command: `npm run dev -- --host 127.0.0.1 --port ${webPort}`,
      cwd: ".",
      url: `http://127.0.0.1:${webPort}`,
      reuseExistingServer: false,
      stdout: "pipe",
      stderr: "pipe",
      timeout: 120_000,
      env: {
        ...process.env,
        VITE_DEV_API_PROXY_TARGET: `http://127.0.0.1:${apiPort}`,
      },
    },
  ],
});
