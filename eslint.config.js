import js from '@eslint/js';
import globals from 'globals';

/** 第三方与产物目录不参与检查(public/ 只有二进制资产)。 */
const IGNORED = ['node_modules/**', 'dist/**', 'coverage/**', '.npm-cache/**', 'public/**'];

export default [
  { ignores: IGNORED },
  js.configs.recommended,
  {
    files: ['scripts/**/*.js'],
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: 'module',
      globals: { ...globals.browser },
    },
  },
  {
    files: ['tests/**/*.js', '*.config.js'],
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: 'module',
      globals: { ...globals.node },
    },
  },
  {
    rules: {
      // 生产代码不留 console.log;警告与错误属于可诊断输出,放行
      'no-console': ['error', { allow: ['warn', 'error'] }],
      'no-unused-vars': ['error', { argsIgnorePattern: '^_', caughtErrors: 'none' }],
      'prefer-const': 'error',
      eqeqeq: ['error', 'always', { null: 'ignore' }],
    },
  },
];
