import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// All API calls go to /api/* and are proxied to FastAPI, so the browser
// only ever talks to localhost:5173 (no CORS issues in development).
export default defineConfig({
  plugins: [react()],
  server: {
    host: "localhost",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
