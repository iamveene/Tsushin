export const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export function validateEmailAddress(email: string): string | null {
  const value = email.trim()

  if (!value) {
    return 'Email address is required'
  }

  if (!EMAIL_PATTERN.test(value)) {
    return 'Enter a valid email address'
  }

  return null
}
