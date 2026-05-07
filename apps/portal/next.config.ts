import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  transpilePackages: ["@aigw/ui", "@aigw/charts", "@aigw/hooks", "@aigw/contracts"],
};

export default nextConfig;
