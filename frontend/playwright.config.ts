import { defineConfig } from "@playwright/test";

// P1-15：未注入 E2E_API_KEY 时明确警告（依赖真实后端 Key 的用例将静默 skip），
// 一键入口见 scripts/e2e_up.sh（Linux/macOS/Git Bash）与 scripts/e2e_up.ps1（Windows）。
if (!process.env.E2E_API_KEY) {
  console.warn(
    "[e2e] E2E_API_KEY 未设置：依赖真实后端 Key 的用例将跳过。" +
      "运行 scripts/e2e_up.sh 或 scripts/e2e_up.ps1 可自动准备隔离库、签发 Key 并注入。",
  );
}

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
      // P1-15：把 E2E_API_KEY 透传给 webServer 环境（Playwright 会与 process.env 合并），
      // 保证 CI/Linux 上无需 PowerShell 入口也能整链路注入。
      env: { VITE_API_BASE_URL: "http://127.0.0.1:8001", E2E_API_KEY: process.env.E2E_API_KEY ?? "" },
      timeout: 60_000,
      reuseExistingServer: false,
    },
  ],
});
