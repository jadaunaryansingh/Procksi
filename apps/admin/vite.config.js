import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  server: {
    port: 3000,
    strictPort: true,
    allowedHosts: true,
    watch: {
      // Use polling on Windows Docker to detect file changes via volume mounts
      usePolling: true,
      interval: 300,
    },
  },
  preview: {
    allowedHosts: true,
  },
});
