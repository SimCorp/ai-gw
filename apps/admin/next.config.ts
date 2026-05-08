import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  transpilePackages: ["@aigw/ui", "@aigw/charts", "@aigw/hooks", "@aigw/contracts"],
};

export default nextConfig;
