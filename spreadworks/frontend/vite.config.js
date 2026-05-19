import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    // Splitting heavy vendor libs into named chunks lets the browser cache
    // them independently from app code and parallelize downloads. Plotly +
    // Recharts are >2 MB combined and only used on /gex-profile, so they
    // no longer block first paint on /, /positions, or /bots/*.
    rollupOptions: {
      output: {
        manualChunks: (id) => {
          if (!id.includes('node_modules')) return;
          if (id.includes('plotly')) return 'vendor-plotly';
          if (id.includes('recharts') || id.includes('d3-')) return 'vendor-recharts';
          if (id.includes('react-router')) return 'vendor-router';
          if (id.includes('lucide-react')) return 'vendor-icons';
          if (id.includes('react-dom') || id.includes('/react/') || id.endsWith('/react')) {
            return 'vendor-react';
          }
        },
      },
    },
    chunkSizeWarningLimit: 1200,
  },
});
