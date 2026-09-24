import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  use: { baseURL: "http://127.0.0.1:5173" },
  webServer: [
    {
      command: "python -m uvicorn api.main:app --port 8001",
      cwd: "..",
      port: 8001,
      env: { DB_PATH: ".e2e/query.db" },
      timeout: 60_000,
      reuseExistingServer: false,
    },
    {
      command: "npx vite --port 5173 --strictPort",
      port: 5173,
      env: { VITE_API_BASE_URL: "http://127.0.0.1:8001" },
      timeout: 60_000,
      reuseExistingServer: false,
    },
  ],
});
