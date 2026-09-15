import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Minimal self-contained server bundle for the Docker image (see web/Dockerfile) —
  // doesn't change `next dev`/`next build` output for local (non-Docker) use.
  output: "standalone",
};

export default nextConfig;
