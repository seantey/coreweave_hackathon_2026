import { defineConfig } from "vite";
export default defineConfig({
  build: { rollupOptions: { input: { workspace: 'index.html', demo: 'demo.html' } } },
  server: {
    port: 5173,
    strictPort: true,
    watch: { usePolling: true, interval: 500 },
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/media": "http://127.0.0.1:8000",
    },
  },
});
