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
  // frontend (cookie-scoped). In standalone builds, rewrites are evaluated at
  // image build time, so compose passes BACKEND_INTERNAL_URL as both a build
  // arg and a runtime env var. Default targets the stack-scoped compose
  // backend on its in-network port 8081.
  //
  // Keep these as fallback rewrites so first-party route handlers such as
  // /api/auth/[...path] can normalize HTTP cookie/security headers before
  // requests are forwarded to the backend.
  async rewrites() {
    const stackName = process.env.TSN_STACK_NAME?.trim()
    const backend =
      process.env.BACKEND_INTERNAL_URL ||
      (stackName ? `http://${stackName}-backend:8081` : 'http://backend:8081')
    return {
      fallback: [
        { source: '/api/:path*', destination: `${backend}/api/:path*` },
        { source: '/ws/:path*', destination: `${backend}/ws/:path*` },
      ],
    }
  },
}

export default nextConfig
