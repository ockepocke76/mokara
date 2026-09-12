import type { NextConfig } from "next";
import createMDX from "@next/mdx";

const nextConfig: NextConfig = {
  pageExtensions: ["ts", "tsx", "mdx"],
  // Self-contained server bundle for the Docker image (W7).
  output: "standalone",
};

const withMDX = createMDX({});

export default withMDX(nextConfig);
