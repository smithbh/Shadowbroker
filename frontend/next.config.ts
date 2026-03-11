import type { NextConfig } from "next";

// BACKEND_URL is a plain (non-NEXT_PUBLIC_) env var read at server startup —
// not baked at build time — so it can be set in docker-compose `environment`.
// Defaults to localhost for local dev where both services run on the same host.
const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  transpilePackages: ['react-map-gl', 'mapbox-gl', 'maplibre-gl'],
  output: "standalone",
  typescript: {
    ignoreBuildErrors: true,
  },
  eslint: {
    ignoreDuringBuilds: true,
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
