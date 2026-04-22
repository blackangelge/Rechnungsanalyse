import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // StrictMode in dev führt zu doppelten useEffect-Aufrufen → zwei parallele API-Anfragen
  // und kann Hydration-Probleme auf dem NAS/Docker-Setup verursachen
  reactStrictMode: false,
  // NAS-Hostname muss explizit erlaubt werden, sonst blockiert Next.js 16
  // cross-origin Anfragen zu /_next/webpack-hmr (HMR WebSocket)
  allowedDevOrigins: ["nas", "192.168.16.4"],
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
