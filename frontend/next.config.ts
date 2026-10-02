import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Self-contained server bundle for the Docker image.
  output: "standalone",
  poweredByHeader: false,
  // The map is the home page now.
  async redirects() {
    return [{ source: "/map", destination: "/", permanent: false }];
  },
  experimental: {
    // Field reports carry up to 4 photos of 8 MB each (the backend's limits), plus
    // form fields and multipart overhead. Both limits default far lower: 1 MB for
    // Server Actions, and proxy.ts silently truncates bodies over 10 MB.
    serverActions: { bodySizeLimit: "34mb" },
    proxyClientMaxBodySize: "34mb",
  },
};

export default nextConfig;
