'use client'

/**
 * Danger Zone Component
 * Displays dangerous actions like deleting organization
 */

import { useState } from 'react'
import { AlertTriangleIcon } from '@/components/ui/icons'

export default function DangerZone() {
  const [showConfirm, setShowConfirm] = useState(false)
  const [confirmText, setConfirmText] = useState('')

  const handleDelete = () => {
    if (confirmText === 'DELETE') {
      alert('Organization deleted (mock)')
      setShowConfirm(false)
    }
  }

  return (
    <div className="mt-8 p-6 border-2 border-red-300 dark:border-red-800 rounded-lg bg-red-50 dark:bg-red-900/10">
      <h3 className="text-lg font-semibold text-red-900 dark:text-red-100 mb-2 flex items-center gap-2">
        <AlertTriangleIcon size={20} /> Danger Zone
      </h3>
      <p className="text-sm text-red-800 dark:text-red-200 mb-4">
        Deleting your organization is permanent and cannot be undone. All data, including agents,
        contacts, memory, and integrations will be permanently deleted.
      </p>

      {!showConfirm ? (
        <button
          onClick={() => setShowConfirm(true)}
          className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white text-sm font-medium rounded-md transition-colors"
        >
          Delete Organization
        </button>
      ) : (
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-red-900 dark:text-red-100 mb-2">
              Type <strong>DELETE</strong> to confirm:
            </label>
            <input
              type="text"
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              className="w-full max-w-md px-3 py-2 border dark:border-red-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800 focus:ring-2 focus:ring-red-500"
              placeholder="DELETE"
            />
          </div>
          <div className="flex items-center space-x-3">
            <button
              onClick={handleDelete}
              disabled={confirmText !== 'DELETE'}
              className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white text-sm font-medium rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              I understand, delete my organization
            </button>
            <button
              onClick={() => {
                setShowConfirm(false)
                setConfirmText('')
              }}
              className="px-4 py-2 bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 text-gray-900 dark:text-gray-100 text-sm font-medium rounded-md transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
