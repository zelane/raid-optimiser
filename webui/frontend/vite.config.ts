// Vite over webui/frontend: `npm run build` writes webui/static/dist (with its manifest, which
// webui/inertia.py reads for the page shell's tags and the asset version); `npm run dev` serves
// the same entry with hot reload (the shell points at it when VITE_DEV is set).
import vue from "@vitejs/plugin-vue";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

const here = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  root: here,
  base: "/static/dist/",
  plugins: [vue()],
  server: { host: "127.0.0.1", port: 5173, strictPort: true, origin: "http://127.0.0.1:5173" },
  build: {
    outDir: fileURLToPath(new URL("../static/dist", import.meta.url)),
    emptyOutDir: true,
    manifest: true,
    rollupOptions: { input: "src/app.ts" },
  },
});
