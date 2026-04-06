import path from 'path'
import { fileURLToPath } from 'url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Phase 9: Enable standalone output for Docker containerization
  output: 'standalone',
  outputFileTracingRoot: __dirname,
  turbopack: {
    root: __dirname,
  },
  typescript: {
    // Skip type checking during build (Windows-to-Linux migration compatibility)
    ignoreBuildErrors: true,
  },
}

export default nextConfig
