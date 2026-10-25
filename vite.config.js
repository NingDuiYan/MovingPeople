import { defineConfig } from 'vite';

export default defineConfig({
  // 相对基址:dist/ 可以放在任意子目录或静态托管上直接打开
  base: './',
  server: {
    host: '0.0.0.0',
    port: 5173,
    open: false,
  },
  build: {
    target: 'es2020',
    outDir: 'dist',
    // three 与 examples 合起来体积较大,单 chunk 属预期,不用报警告
    chunkSizeWarningLimit: 1600,
  },
});
