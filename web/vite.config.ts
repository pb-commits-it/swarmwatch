import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The built UI ships inside the Python package so `pip install swarmwatch`
// serves it with no Node toolchain. `base: "./"` keeps asset paths relative so
// it also works when mounted under a subpath (e.g. /swarmwatch/) on the VM.
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: "../swarmwatch/web",
    emptyOutDir: true,
  },
  server: {
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
});
