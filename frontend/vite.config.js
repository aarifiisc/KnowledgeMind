import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies /api to the FastAPI backend so `npm run dev` works against
// `python launcher.py`. Production build (npm run build -> dist/) is served by
// FastAPI itself (single deploy) or by Vercel (pointing at VITE_API_BASE).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  build: { outDir: "dist", emptyOutDir: true },
});
