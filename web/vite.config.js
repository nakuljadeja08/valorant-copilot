import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Static build only: `public/data` is copied verbatim, so the deployed bundle is
// HTML/JS plus the pre-generated JSON. No server, no env vars, no key material.
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: { outDir: "dist", sourcemap: false },
});
