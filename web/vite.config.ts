import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss()],
  define: {
    __BUILD_MODE__: JSON.stringify(mode),
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (id.includes('node_modules')) {
            if (id.includes('react-router') || id.includes('/react/') || id.includes('/react-dom/')) return 'vendor'
            if (id.includes('framer-motion')) return 'motion'
            if (id.includes('/d3-')) return 'd3'
          }
        },
      },
    },
  },
}))
