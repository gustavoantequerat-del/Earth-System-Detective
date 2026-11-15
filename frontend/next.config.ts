import type { NextConfig } from 'next';

const config: NextConfig = {
  async rewrites() {
    const backend = process.env.BACKEND_URL ?? (process.env.VERCEL === '1' ? undefined : 'http://127.0.0.1:3001');
    if (!backend) return [];
    return [{ source: '/api/:path*', destination: `${backend.replace(/\/$/, '')}/api/:path*` }];
  },
};

export default config;
