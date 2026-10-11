import { defineConfig } from "vitest/config";

/**
 * P1-14：单测只收集 src/ 下的用例，显式排除 e2e/（Playwright spec 交给 `npm run test:e2e`），
 * 避免 vitest 误加载 Playwright 测试文件导致 `npm test` 开箱即挂。
 */
export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    exclude: ["e2e/**", "dist/**", "node_modules/**"],
  },
});
