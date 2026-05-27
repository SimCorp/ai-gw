import type { NextConfig } from "next";

const adminApi = process.env.NEXT_PUBLIC_ADMIN_API ?? 'http://localhost:8005';

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  {
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
      "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
      "img-src 'self' data: blob:",
      `connect-src 'self' ${adminApi} http://localhost:8080`,
      "font-src 'self' https://fonts.gstatic.com",
      "frame-ancestors 'none'",
    ].join("; "),
  },
];

const nextConfig: NextConfig = {
  basePath: "/admin-portal",
  output: "standalone",
  transpilePackages: ["@aigw/ui", "@aigw/charts", "@aigw/hooks", "@aigw/contracts"],
  async headers() {
    return [{ source: "/(.*)", headers: securityHeaders }];
  },
};

export default nextConfig;
