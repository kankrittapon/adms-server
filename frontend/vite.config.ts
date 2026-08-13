import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// F2 development server. The ADMS API is at VITE_API_BASE_URL (default
// http://192.168.1.248:8081) and already allows this origin via CORS
// (API_CORS_ORIGINS=http://localhost:5173).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
  },
});
