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
    // outDir 在项目根外 (src/dist), vite 默认不清空 → 每次 build 堆积历史
    // bundle 死代码, 最后全被打进 exe 虚胖。显式清空 (纯 build 产物目录, 无风险)。
    emptyOutDir: true,
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
