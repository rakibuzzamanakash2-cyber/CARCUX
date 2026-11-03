import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Self-contained server bundle for the Docker image.
  output: "standalone",
  poweredByHeader: false,
  // Browser-side protections on every page. The CSP limits framing, plugins, <base> and
  // form targets only; scripts are left to Next.js, whose inline bootstrap needs them.
  async headers() {
    const security = [
      {
        key: "Content-Security-Policy",
        value: "frame-ancestors 'none'; object-src 'none'; base-uri 'self'; form-action 'self'",
      },
      { key: "X-Frame-Options", value: "DENY" },
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
      { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(self)" },
      ...(process.env.NODE_ENV === "production"
        ? [{ key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" }]
        : []),
    ];
    return [{ source: "/:path*", headers: security }];
  },
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
