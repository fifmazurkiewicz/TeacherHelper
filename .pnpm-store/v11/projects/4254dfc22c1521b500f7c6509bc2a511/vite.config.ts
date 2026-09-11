import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const backendUrl = (env.BACKEND_INTERNAL_URL || "http://127.0.0.1:8080").replace(/\/+$/, "");

  return {
    plugins: [react()],
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
    },
  };
});
