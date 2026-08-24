/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  // 锚定 tracing root 为应用目录本身：保证 standalone 输出固定为
  // .next/standalone/server.js（Dockerfile 与 CI 启动脚本均依赖该布局），
  // 同时避免仓库外层杂散 lockfile 干扰 workspace root 推断。
  outputFileTracingRoot: __dirname,
  async rewrites() {
    const apiBase = process.env.API_BASE_URL || 'http://localhost:8000';
    return [
      {
        source: '/api/:path*',
        destination: `${apiBase}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
