import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "rywfqirgkbdjqdyggybb.supabase.co" },
      { protocol: "https", hostname: "www.procyclingstats.com" },
    ],
    formats: ["image/avif", "image/webp"],
  },
};

export default nextConfig;
