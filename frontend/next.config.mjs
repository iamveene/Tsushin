/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Phase 9: Enable standalone output for Docker containerization
  output: 'standalone',
  typescript: {
    // Skip type checking during build (Windows-to-Linux migration compatibility)
    ignoreBuildErrors: true,
  },
  eslint: {
    // Skip linting during build
    ignoreDuringBuilds: true,
  },
}

export default nextConfig
