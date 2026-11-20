import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The experiment service is read by the Node layer only (server components and
  // route handlers), never by the browser. Keeping it off the client means the
  // Python service needs no public CORS in production.
  reactStrictMode: true,
};

export default nextConfig;
