/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  async rewrites() {
    // When accessing the web container directly on :3000, /api/* would normally 404.
    // This proxies /api/* to the FastAPI backend so both :3000 and nginx(:8080) work.
    const base =
      process.env.INTERNAL_API_BASE ||
      process.env.API_PROXY_TARGET ||
      // Default for docker-compose network (api service).
      "http://api:8000";

    const target = String(base).replace(/\/$/, "");
    // Backend routes are mounted at "/" (nginx adds the "/api" prefix externally).
    return [{ source: "/api/:path*", destination: `${target}/:path*` }];
  },
};

module.exports = nextConfig;
