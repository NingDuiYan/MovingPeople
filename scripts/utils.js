// ============ 静态资产工具 ============

/**
 * 静态资产 URL:public/ 下的文件按 Vite 的 BASE_URL 拼接。
 * BASE_URL 以 '/' 结尾,dev 为 '/',build 为相对基址,子目录部署也不会拼错。
 */
export const assetUrl = (path) => `${import.meta.env.BASE_URL}${path}`;
