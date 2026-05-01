import path from 'path'
import { fileURLToPath } from 'url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: 'standalone',
  outputFileTracingRoot: __dirname,
  turbopack: {
    root: __dirname,
  },
  typescript: {
    ignoreBuildErrors: true,
  },
  // v0.6.1 BUG-5/7/8 fix: proxy /api/* and /ws/* to the backend over the
  // internal Docker network so browser requests stay same-origin with the
  // frontend (cookie-scoped). BACKEND_INTERNAL_URL is read at request time
  // from the Node.js process (NOT a build arg). Default targets the compose
  // stack-scoped compose backend on its in-network port 8081.
  async rewrites() {
    const stackName = process.env.TSN_STACK_NAME?.trim()
    const backend =
      process.env.BACKEND_INTERNAL_URL ||
      (stackName ? `http://${stackName}-backend:8081` : 'http://backend:8081')
    return [
      { source: '/api/:path*', destination: `${backend}/api/:path*` },
      { source: '/ws/:path*', destination: `${backend}/ws/:path*` },
    ]
  },
}

export default nextConfig
