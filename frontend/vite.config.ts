import { sentryVitePlugin } from "@sentry/vite-plugin";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const backendUrl = (env.BACKEND_INTERNAL_URL || "http://127.0.0.1:8080").replace(/\/+$/, "");

  return {
    plugins: [react(), ...(process.env.SENTRY_AUTH_TOKEN ? [sentryVitePlugin({
      authToken: process.env.SENTRY_AUTH_TOKEN,
      org: process.env.SENTRY_ORG,
      project: process.env.SENTRY_PROJECT,
      telemetry: false,
      sourcemaps: { filesToDeleteAfterUpload: ["./dist/**/*.map"] },
    })] : [])],
    resolve: {
      alias: { "@": path.resolve(__dirname, "src") },
    },
    server: {
      host: "127.0.0.1",
      port: 18080,
      // Tunel (ngrok itd.) — inaczej: „This host is not allowed”
      allowedHosts: [".ngrok-free.app", ".ngrok.io", ".ngrok.app"],
      proxy: {
        "/th-api": {
          target: backendUrl,
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/th-api/, ""),
        },
      },
    },
    build: {
      outDir: "dist",
      sourcemap: process.env.SENTRY_AUTH_TOKEN ? "hidden" : false,
    },
  };
});
