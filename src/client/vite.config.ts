import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// 桥端口: 开发时 vite 把 /api 代理到 Python 桥, 前端走相对路径不写死端口。
// 桥真实端口由 start_gui.py 动态探测 (被占 +1), 写进 VITE_BRIDGE_PORT;
// 默认 8642。
const BRIDGE_PORT = process.env.VITE_BRIDGE_PORT || '8642';

export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    outDir: '../dist',
  },
  server: {
    port: 3000,
    proxy: {
      // /api/* 代理到 Python FastAPI 桥 (规则/Agent/出图/RAG 全部走这里)
      '/api': {
        target: `http://127.0.0.1:${BRIDGE_PORT}`,
        changeOrigin: true,
      },
    },
  },
});
