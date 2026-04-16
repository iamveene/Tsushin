'use client'

import React, { createContext, useContext, useState, useCallback, useRef } from 'react'

export type ToastType = 'success' | 'error' | 'warning' | 'info'

export interface Toast {
  id: string
  type: ToastType
  title: string
  message?: string
  duration: number
}

interface ToastContextValue {
  toasts: Toast[]
  addToast: (type: ToastType, title: string, message?: string, duration?: number) => void
  removeToast: (id: string) => void
  success: (title: string, message?: string, duration?: number) => void
  error: (title: string, message?: string, duration?: number) => void
  warning: (title: string, message?: string, duration?: number) => void
  info: (title: string, message?: string, duration?: number) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

const MAX_TOASTS = 5

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const timersRef = useRef<Map<string, NodeJS.Timeout>>(new Map())

  const removeToast = useCallback((id: string) => {
    const timer = timersRef.current.get(id)
    if (timer) {
      clearTimeout(timer)
      timersRef.current.delete(id)
    }
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  const addToast = useCallback((type: ToastType, title: string, message?: string, duration: number = 4000) => {
    const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
    const toast: Toast = { id, type, title, message, duration }

    setToasts(prev => {
      const next = [...prev, toast]
      // If exceeding max, remove oldest
      if (next.length > MAX_TOASTS) {
        const removed = next.shift()
        if (removed) {
          const timer = timersRef.current.get(removed.id)
          if (timer) {
            clearTimeout(timer)
            timersRef.current.delete(removed.id)
          }
        }
      }
      return next
    })

    // Auto-dismiss
    const timer = setTimeout(() => {
      removeToast(id)
    }, duration)
    timersRef.current.set(id, timer)
  }, [removeToast])

  const success = useCallback((title: string, message?: string, duration?: number) => {
    addToast('success', title, message, duration)
  }, [addToast])

  const error = useCallback((title: string, message?: string, duration?: number) => {
    addToast('error', title, message, duration)
  }, [addToast])

  const warning = useCallback((title: string, message?: string, duration?: number) => {
    addToast('warning', title, message, duration)
  }, [addToast])

  const info = useCallback((title: string, message?: string, duration?: number) => {
    addToast('info', title, message, duration)
  }, [addToast])

  return (
    <ToastContext.Provider value={{ toasts, addToast, removeToast, success, error, warning, info }}>
      {children}
    </ToastContext.Provider>
  )
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext)
  if (!ctx) {
    throw new Error('useToast must be used within a ToastProvider')
  }
  return ctx
}
