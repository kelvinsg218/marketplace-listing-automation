import type { NextConfig } from "next";

// Production: static export (no Node server). FastAPI or nginx serves `out/` on the same origin as /api.
// Development: `next dev` proxies /api to the local FastAPI, so cookies stay same-origin there too.
const isDev = process.env.NODE_ENV !== "production";
const apiOrigin = process.env.MLA_API_ORIGIN ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  ...(isDev
    ? { rewrites: async () => [{ source: "/api/:path*", destination: `${apiOrigin}/api/:path*` }] }
    : { output: "export" }),
  trailingSlash: true,
  images: { unoptimized: true },
  poweredByHeader: false,
};

export default nextConfig;
