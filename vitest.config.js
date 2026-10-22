import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    include: ['tests/**/*.test.js'],
    environment: 'node',
    // 用 worker_threads 而不是子进程:CI 与本机沙箱下都不依赖 piped stdio
    pool: 'threads',
  },
});
