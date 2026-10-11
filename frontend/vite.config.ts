import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

/**
 * P1-25：开发模式下摘除 index.html 中的 CSP meta。
 * @vitejs/plugin-react 在 dev 注入 react-refresh 内联 <script> preamble、HMR 走 ws://，
 * 会被严格的 CSP 拦截；生产构建（vite build）不经过该插件，CSP 保持严格生效。
 */
const stripCspInDev: Plugin = {
  name: "strip-csp-in-dev",
  apply: "serve",
  transformIndexHtml(html) {
    return html.replace(/<meta\s+http-equiv=["']Content-Security-Policy["'][^>]*>/i, "");
  },
};

export default defineConfig({
  plugins: [react(), stripCspInDev],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
