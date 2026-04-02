'use client'

/**
 * Authentication Context
 * Provides authentication state and methods throughout the application
 * Phase 7.6.3 - Real Backend Authentication
 */

import React, { createContext, useContext, useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/client'

// User type matching backend response
interface User {
  id: number
  email: string
  full_name: string
  tenant_id: number
  tenant_name?: string | null
  is_global_admin: boolean
  is_active?: boolean
  email_verified?: boolean
  permissions?: string[]
  created_at?: string | null
  last_login_at?: string | null
}

interface AuthContextType {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  loginWithGoogle: (options?: { tenantSlug?: string; redirectAfter?: string; invitationToken?: string }) => Promise<void>
  setAuthFromToken: (token: string) => Promise<void>
  signup: (data: {
    email: string
    password: string
    name: string
    orgName: string
  }) => Promise<void>
  logout: () => void
  forgotPassword: (email: string) => Promise<void>
  hasPermission: (permission: string) => boolean
  isGlobalAdmin: boolean
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

// SEC-005 Phase 3: localStorage token storage removed entirely.
// All auth now relies on httpOnly cookie (tsushin_session) set by backend.
// localStorage cleanup for users upgrading from previous versions.
const _cleanupLegacyToken = () => {
  if (typeof window !== 'undefined') {
    localStorage.removeItem('tsushin_auth_token')
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const router = useRouter()

  // Load user from httpOnly cookie on mount
  useEffect(() => {
    const loadUser = async () => {
      // Clean up legacy localStorage token from previous versions
      _cleanupLegacyToken()
      try {
        const userData = await api.getCurrentUser()
        setUser(userData)
      } catch (error) {
        // No valid session cookie — user is not authenticated
        console.debug('No active session:', error)
        setUser(null)
      }
      setLoading(false)
    }
    loadUser()
  }, [])

  const login = async (email: string, password: string) => {
    const response = await api.login(email, password)
    // SEC-005: Cookie is set by backend response — no localStorage needed
    setUser(response.user)

    // Redirect based on user type
    if (response.user.is_global_admin) {
      router.push('/system/integrations')
    } else {
      router.push('/')
    }
  }

  const loginWithGoogle = async (options?: {
    tenantSlug?: string
    redirectAfter?: string
    invitationToken?: string
  }) => {
    try {
      const response = await api.getGoogleAuthURL(options)
      // Redirect to Google OAuth
      window.location.href = response.auth_url
    } catch (error) {
      console.error('Failed to start Google login:', error)
      throw error
    }
  }

  const setAuthFromToken = async (_token: string) => {
    // SEC-005: The httpOnly cookie was already set by the backend response
    // that returned this token. We just need to load the user profile via cookie.
    try {
      const userData = await api.getCurrentUser()
      setUser(userData)
      // Note: Redirect is handled by the SSO callback page
    } catch (error) {
      throw error
    }
  }

  const signup = async (data: {
    email: string
    password: string
    name: string
    orgName: string
  }) => {
    const response = await api.signup({
      email: data.email,
      password: data.password,
      full_name: data.name,
      org_name: data.orgName,
    })
    // SEC-005: Cookie is set by backend response — no localStorage needed
    setUser(response.user)
    router.push('/')
  }

  const logout = () => {
    // SEC-005: Call logout endpoint — backend clears the httpOnly cookie
    api.logout().catch(console.error)
    _cleanupLegacyToken()
    setUser(null)
    router.push('/auth/login')
  }

  const forgotPasswordHandler = async (email: string) => {
    await api.requestPasswordReset(email)
  }

  const checkPermission = (permission: string): boolean => {
    if (!user) return false
    if (user.is_global_admin) return true
    return user.permissions?.includes(permission) || false
  }

  const isGlobalAdmin = user?.is_global_admin || false

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        login,
        loginWithGoogle,
        setAuthFromToken,
        signup,
        logout,
        forgotPassword: forgotPasswordHandler,
        hasPermission: checkPermission,
        isGlobalAdmin,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}

/**
 * Hook to require authentication
 * Redirects to login if not authenticated
 */
export function useRequireAuth() {
  const { user, loading, hasPermission } = useAuth()
  const router = useRouter()
  const pathname = typeof window !== 'undefined' ? window.location.pathname : ''

  useEffect(() => {
    // Skip auth redirect for public pages (login, signup, setup, etc.)
    const isPublicPage = pathname.startsWith('/auth') || pathname.startsWith('/setup')
    if (!loading && !user && !isPublicPage) {
      router.push('/auth/login')
    }
  }, [user, loading, router, pathname])

  return { user, loading, hasPermission }
}

/**
 * Hook to require global admin
 * Redirects to home if not global admin
 */
export function useRequireGlobalAdmin() {
  const { user, loading, isGlobalAdmin } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!loading) {
      if (!user) {
        router.push('/auth/login')
      } else if (!isGlobalAdmin) {
        router.push('/')
      }
    }
  }, [user, loading, isGlobalAdmin, router])

  return { user, loading }
}

// Export types for use elsewhere
export type { User }
