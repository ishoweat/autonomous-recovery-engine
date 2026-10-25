/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  ...(!process.env.NETLIFY ? { output: "standalone" } : {}),
  experimental: {
    typedRoutes: true
  },
  async rewrites() {
    const backendUrl =
      process.env.NEXT_PUBLIC_API_BASE_URL ||
      process.env.NEXT_PUBLIC_API_URL ||
      "http://127.0.0.1:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
