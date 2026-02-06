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

// Token storage utilities
const TOKEN_KEY = 'tsushin_auth_token'

const storeToken = (token: string) => {
  localStorage.setItem(TOKEN_KEY, token)
}

const getToken = (): string | null => {
  return localStorage.getItem(TOKEN_KEY)
}

const removeToken = () => {
  localStorage.removeItem(TOKEN_KEY)
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const router = useRouter()

  // Load user from token on mount
  useEffect(() => {
    const loadUser = async () => {
      const token = getToken()
      if (token) {
        try {
          const userData = await api.getCurrentUser(token)
          setUser(userData)
        } catch (error) {
          console.error('Failed to load user:', error)
          removeToken()
          setUser(null)
        }
      }
      setLoading(false)
    }
    loadUser()
  }, [])

  const login = async (email: string, password: string) => {
    const response = await api.login(email, password)
    storeToken(response.access_token)
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

  const setAuthFromToken = async (token: string) => {
    // Store the token
    storeToken(token)

    // Fetch user info
    try {
      const userData = await api.getCurrentUser(token)
      setUser(userData)

      // Note: Redirect is handled by the SSO callback page
    } catch (error) {
      removeToken()
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
    storeToken(response.access_token)
    setUser(response.user)
    router.push('/')
  }

  const logout = () => {
    const token = getToken()
    if (token) {
      // Call logout endpoint (fire and forget)
      api.logout(token).catch(console.error)
    }
    removeToken()
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

  useEffect(() => {
    if (!loading && !user) {
      router.push('/auth/login')
    }
  }, [user, loading, router])

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

// Export types and utilities for use elsewhere
export type { User }
export { getToken }
