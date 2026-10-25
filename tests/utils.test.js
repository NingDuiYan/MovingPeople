// ============ utils.js 单测:静态资产路径拼接 ============
import { describe, expect, it } from 'vitest';
import { assetUrl } from '../scripts/utils.js';

describe('assetUrl', () => {
  it('把 public/ 下的相对路径拼到 BASE_URL 后面,不会拼出双斜杠', () => {
    const url = assetUrl('models/wasteland_scene.glb');
    expect(url.endsWith('models/wasteland_scene.glb')).toBe(true);
    expect(url).not.toContain('//');
  });
});
