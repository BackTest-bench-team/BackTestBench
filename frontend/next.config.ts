import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: path.join(__dirname, ".."),
  // Hide the Next.js devtools pill ("N · 1 Issue") in local development.
  devIndicators: false,
};

export default nextConfig;