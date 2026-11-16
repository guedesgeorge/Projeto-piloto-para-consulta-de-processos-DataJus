import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    // Em desenvolvimento, as chamadas /api vão para o FastAPI
    proxy: { '/api': 'http://localhost:8000' },
  },
});
