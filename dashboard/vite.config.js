import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In the cluster the Ingress sends /api to the gateway, so the browser only ever talks to one origin.
// This proxy gives the same single-origin behaviour when you run `npm run dev` on your own machine.
const gateway = process.env.GATEWAY_URL || "http://localhost:9000";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": gateway } },
  preview: { port: 5173, proxy: { "/api": gateway } },
});