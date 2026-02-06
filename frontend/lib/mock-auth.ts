/**
 * Mock Authentication Library
 * Simulates JWT authentication without backend calls
 * Used for UX development before backend implementation
 */

export interface MockUser {
  id: number
  email: string
  name: string
  role: string
  tenant_id: string | null
  tenant_name: string | null
  is_global_admin: boolean
  permissions: string[]
  created_at: string
}

// Mock users database
const MOCK_USERS: Record<string, { password: string; user: MockUser }> = {
  'vini@example.com': {
    password: 'password123',
    user: {
      id: 1,
      email: 'vini@example.com',
      name: 'Vinicius',
      role: 'owner',
      tenant_id: 'tenant_abc',
      tenant_name: 'Acme Corp',
      is_global_admin: false,
      permissions: [
        'agents.read',
        'agents.write',
        'agents.delete',
        'agents.execute',
        'contacts.read',
        'contacts.write',
        'users.invite',
        'users.manage',
        'billing.manage',
        'org.settings.write',
      ],
      created_at: '2025-01-01T00:00:00Z',
    },
  },
  'admin@platform.local': {
    password: 'admin123',
    user: {
      id: 2,
      email: 'admin@platform.local',
      name: 'Platform Admin',
      role: 'global_admin',
      tenant_id: null,
      tenant_name: null,
      is_global_admin: true,
      permissions: ['global.*'],
      created_at: '2025-01-01T00:00:00Z',
    },
  },
  'member@example.com': {
    password: 'member123',
    user: {
      id: 3,
      email: 'member@example.com',
      name: 'John Doe',
      role: 'member',
      tenant_id: 'tenant_abc',
      tenant_name: 'Acme Corp',
      is_global_admin: false,
      permissions: ['agents.read', 'agents.write', 'contacts.read', 'contacts.write'],
      created_at: '2025-01-01T00:00:00Z',
    },
  },
}

// Generate a fake JWT token
function generateMockJWT(user: MockUser): string {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  const payload = btoa(
    JSON.stringify({
      sub: user.id,
      email: user.email,
      role: user.role,
      tenant_id: user.tenant_id,
      is_global_admin: user.is_global_admin,
      exp: Date.now() + 7 * 24 * 60 * 60 * 1000, // 7 days
    })
  )
  const signature = btoa('mock-signature')
  return `${header}.${payload}.${signature}`
}

// Parse mock JWT
function parseMockJWT(token: string): MockUser | null {
  try {
    const parts = token.split('.')
    if (parts.length !== 3) return null

    const payload = JSON.parse(atob(parts[1]))
    if (payload.exp < Date.now()) return null

    // Find user from mock database
    const userEntry = Object.values(MOCK_USERS).find((u) => u.user.id === payload.sub)
    return userEntry ? userEntry.user : null
  } catch {
    return null
  }
}

/**
 * Mock login function
 * Simulates API call with 500ms delay
 */
export async function mockLogin(
  email: string,
  password: string
): Promise<{ user: MockUser; token: string }> {
  // Simulate network delay
  await new Promise((resolve) => setTimeout(resolve, 500))

  const userEntry = MOCK_USERS[email]
  if (!userEntry || userEntry.password !== password) {
    throw new Error('Invalid credentials')
  }

  const token = generateMockJWT(userEntry.user)
  return { user: userEntry.user, token }
}

/**
 * Mock signup function
 * Creates a new organization and owner user
 */
export async function mockSignup(data: {
  email: string
  password: string
  name: string
  orgName: string
}): Promise<{ user: MockUser; token: string }> {
  // Simulate network delay
  await new Promise((resolve) => setTimeout(resolve, 800))

  if (MOCK_USERS[data.email]) {
    throw new Error('Email already exists')
  }

  // Create new tenant and user
  const newUser: MockUser = {
    id: Object.keys(MOCK_USERS).length + 1,
    email: data.email,
    name: data.name,
    role: 'owner',
    tenant_id: `tenant_${Date.now()}`,
    tenant_name: data.orgName,
    is_global_admin: false,
    permissions: [
      'agents.read',
      'agents.write',
      'agents.delete',
      'agents.execute',
      'contacts.read',
      'contacts.write',
      'users.invite',
      'users.manage',
      'billing.manage',
      'org.settings.write',
    ],
    created_at: new Date().toISOString(),
  }

  // Store in mock database
  MOCK_USERS[data.email] = {
    password: data.password,
    user: newUser,
  }

  const token = generateMockJWT(newUser)
  return { user: newUser, token }
}

/**
 * Mock password reset request
 */
export async function mockForgotPassword(email: string): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, 500))

  if (!MOCK_USERS[email]) {
    throw new Error('Email not found')
  }

  // In real implementation, would send email
  console.log(`[MOCK] Password reset email sent to ${email}`)
}

/**
 * Mock password reset
 */
export async function mockResetPassword(token: string, newPassword: string): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, 500))

  // In mock, just log success
  console.log(`[MOCK] Password reset successful for token: ${token}`)
}

/**
 * Get current user from stored token
 */
export function getMockCurrentUser(): MockUser | null {
  if (typeof window === 'undefined') return null

  const token = localStorage.getItem('auth_token')
  if (!token) return null

  return parseMockJWT(token)
}

/**
 * Store auth token
 */
export function storeMockToken(token: string): void {
  if (typeof window !== 'undefined') {
    localStorage.setItem('auth_token', token)
  }
}

/**
 * Remove auth token
 */
export function removeMockToken(): void {
  if (typeof window !== 'undefined') {
    localStorage.removeItem('auth_token')
  }
}

/**
 * Check if user has permission
 */
export function hasPermission(user: MockUser | null, permission: string): boolean {
  if (!user) return false

  // Global admin has all permissions
  if (user.is_global_admin || user.permissions.includes('global.*')) {
    return true
  }

  // Check exact match
  if (user.permissions.includes(permission)) {
    return true
  }

  // Check wildcard match (e.g., 'agents.*' matches 'agents.read')
  const parts = permission.split('.')
  for (let i = parts.length; i > 0; i--) {
    const wildcardPerm = parts.slice(0, i).join('.') + '.*'
    if (user.permissions.includes(wildcardPerm)) {
      return true
    }
  }

  return false
}
