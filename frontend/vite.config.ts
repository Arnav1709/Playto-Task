import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  base: process.env.NODE_ENV === 'production' ? '/static/frontend/' : '/',
  build: {
    outDir: '../backend/static/frontend',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
  },
});
