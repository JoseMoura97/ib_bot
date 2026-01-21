/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  async rewrites() {
    const base = process.env.INTERNAL_API_BASE || process.env.API_PROXY_TARGET || "http://api:8000";
    const target = String(base).replace(/\/$/, "");
    // Backend routes are mounted at "/" (nginx adds the "/api" prefix externally).
    return [{ source: "/api/:path*", destination: `${target}/:path*` }];
  },
};

module.exports = nextConfig;

