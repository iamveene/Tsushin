'use client'

/**
 * Billing & Plans Page
 * Shows current plan, payment method, billing history, and upgrade options
 */

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { useAuth } from '@/contexts/AuthContext'
import { api } from '@/lib/client'
import { AlertTriangleIcon } from '@/components/ui/icons'

interface PlanInfo {
  name: string
  price: number | null
  period: string
  features: string[]
  popular?: boolean
}

const PLANS: PlanInfo[] = [
  {
    name: 'Free',
    price: 0,
    period: 'forever',
    features: ['1 team member', '1 agent', '100 requests/month', 'Basic support'],
  },
  {
    name: 'Pro',
    price: 10,
    period: 'month',
    features: [
      '5 team members',
      '10 agents',
      '10,000 requests/month',
      'Priority support',
      'Advanced integrations',
    ],
    popular: true,
  },
  {
    name: 'Team',
    price: 50,
    period: 'month',
    features: [
      '20 team members',
      '50 agents',
      '100,000 requests/month',
      'Priority support',
      'Advanced integrations',
      'Custom workflows',
    ],
  },
  {
    name: 'Enterprise',
    price: null,
    period: 'custom',
    features: [
      'Unlimited team members',
      'Unlimited agents',
      'Unlimited requests',
      'Dedicated support',
      'Custom integrations',
      'SLA guarantee',
      'On-premise deployment',
    ],
  },
]

const BILLING_HISTORY = [
  { id: 1, date: 'Jan 1, 2025', amount: '$10.00', plan: 'Pro', status: 'paid' },
  { id: 2, date: 'Dec 1, 2024', amount: '$10.00', plan: 'Pro', status: 'paid' },
  { id: 3, date: 'Nov 1, 2024', amount: '$10.00', plan: 'Pro', status: 'paid' },
  { id: 4, date: 'Oct 1, 2024', amount: '$0.00', plan: 'Free', status: 'paid' },
]

export default function BillingPage() {
  const { hasPermission } = useAuth()
  const [showPlanComparison, setShowPlanComparison] = useState(false)
  const [currentPlanName, setCurrentPlanName] = useState<string>('free')
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    const fetchPlan = async () => {
      try {
        const tenantInfo = await api.getCurrentTenant()
        if (tenantInfo.plan) {
          setCurrentPlanName(tenantInfo.plan.toLowerCase())
        }
      } catch (error) {
        console.error('Failed to fetch tenant plan:', error)
      } finally {
        setIsLoading(false)
      }
    }
    fetchPlan()
  }, [])

  // Helper to check if a plan is the current one
  const isCurrentPlan = (planName: string) =>
    planName.toLowerCase() === currentPlanName.toLowerCase()

  // Get the active plan info
  const activePlan = PLANS.find((p) => isCurrentPlan(p.name)) || PLANS[0]

  if (!hasPermission('billing.manage')) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-red-900 dark:text-red-100 mb-2">
            Access Denied
          </h3>
          <p className="text-sm text-red-800 dark:text-red-200">
            Only organization owners can access billing information.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100">
            Billing & Plans
          </h1>
          <p className="text-gray-600 dark:text-gray-400 mt-2">
            Manage your subscription and billing information
          </p>
        </div>

        {/* Back to Settings */}
        <Link
          href="/settings"
          className="inline-flex items-center gap-2 text-sm text-teal-400 hover:text-teal-300 mb-6 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          Back to Settings
        </Link>

        {/* Work in Progress Notice */}
        <div className="mb-6 p-4 bg-amber-900/20 border border-amber-700/50 rounded-lg">
          <div className="flex items-center gap-2">
            <AlertTriangleIcon size={18} className="text-amber-400" />
            <span className="text-amber-200 font-medium">Work in Progress</span>
          </div>
          <p className="text-sm text-amber-300/80 mt-1">
            Billing integration is under development. Plan upgrades and payment processing will be available soon.
          </p>
        </div>

        {/* Current Plan */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 mb-6">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-4">
            Current Plan
          </h2>
          {isLoading ? (
            <div className="animate-pulse">
              <div className="h-8 bg-gray-200 dark:bg-gray-700 rounded w-24 mb-2"></div>
              <div className="h-10 bg-gray-200 dark:bg-gray-700 rounded w-32 mb-4"></div>
            </div>
          ) : (
          <div className="flex items-start justify-between">
            <div>
              <div className="flex items-center space-x-3 mb-2">
                <h3 className="text-2xl font-bold text-blue-600 dark:text-blue-400 capitalize">{activePlan.name}</h3>
                <span className="px-2 py-1 bg-blue-100 dark:bg-blue-900/30 text-blue-900 dark:text-blue-200 text-xs font-semibold rounded-full">
                  CURRENT
                </span>
              </div>
              <p className="text-3xl font-bold text-gray-900 dark:text-gray-100 mb-1">
                {activePlan.price !== null ? `$${activePlan.price}` : 'Custom'}
                {activePlan.price !== null && (
                <span className="text-lg font-normal text-gray-600 dark:text-gray-400">
                  /{activePlan.period}
                </span>
                )}
              </p>
              {activePlan.price !== null && activePlan.price > 0 && (
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                  Next billing date: {new Date(new Date().setMonth(new Date().getMonth() + 1)).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                </p>
              )}
              <div className="space-y-2">
                {activePlan.features.map((feature, idx) => (
                  <div key={idx} className="flex items-center space-x-2 text-sm">
                    <span className="text-green-600 dark:text-green-400">✓</span>
                    <span className="text-gray-700 dark:text-gray-300">{feature}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="flex flex-col space-y-2">
              <button
                onClick={() => setShowPlanComparison(!showPlanComparison)}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-md transition-colors"
              >
                {showPlanComparison ? 'Hide Plans' : 'View All Plans'}
              </button>
              <button className="px-4 py-2 bg-red-100 dark:bg-red-900/30 text-red-900 dark:text-red-200 font-medium rounded-md hover:bg-red-200 dark:hover:bg-red-900/50 transition-colors">
                Cancel Subscription
              </button>
            </div>
          </div>
          )}
        </div>

        {/* Plan Comparison */}
        {showPlanComparison && (
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 mb-6">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-6">
              Compare Plans
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
              {PLANS.map((plan) => (
                <div
                  key={plan.name}
                  className={`relative border-2 rounded-lg p-6 ${
                    isCurrentPlan(plan.name)
                      ? 'border-blue-500 dark:border-blue-400'
                      : 'border-gray-200 dark:border-gray-700'
                  }`}
                >
                  {plan.popular && (
                    <div className="absolute top-0 right-0 transform translate-x-2 -translate-y-2">
                      <span className="px-3 py-1 bg-blue-600 text-white text-xs font-bold rounded-full">
                        POPULAR
                      </span>
                    </div>
                  )}

                  <h3 className="text-xl font-bold text-gray-900 dark:text-gray-100 mb-2">
                    {plan.name}
                  </h3>
                  <div className="mb-4">
                    <span className="text-3xl font-bold text-gray-900 dark:text-gray-100">
                      {plan.price ? `$${plan.price}` : 'Custom'}
                    </span>
                    {plan.price !== null && (
                      <span className="text-gray-600 dark:text-gray-400">/{plan.period}</span>
                    )}
                  </div>

                  <ul className="space-y-2 mb-6">
                    {plan.features.map((feature, idx) => (
                      <li key={idx} className="flex items-start space-x-2 text-sm">
                        <span className="text-green-600 dark:text-green-400 mt-0.5">✓</span>
                        <span className="text-gray-700 dark:text-gray-300">{feature}</span>
                      </li>
                    ))}
                  </ul>

                  <button
                    disabled={isCurrentPlan(plan.name)}
                    className={`w-full py-2 rounded-md font-medium transition-colors ${
                      isCurrentPlan(plan.name)
                        ? 'bg-gray-200 dark:bg-gray-700 text-gray-500 dark:text-gray-400 cursor-not-allowed'
                        : 'bg-blue-600 hover:bg-blue-700 text-white'
                    }`}
                  >
                    {isCurrentPlan(plan.name) ? 'Current Plan' : plan.price ? 'Upgrade' : 'Contact Sales'}
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Payment Method */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 mb-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
              Payment Method
            </h2>
            <button className="text-sm text-blue-600 dark:text-blue-400 hover:underline">
              Update
            </button>
          </div>
          <div className="flex items-center space-x-4 p-4 border border-gray-200 dark:border-gray-700 rounded-lg">
            <div className="w-12 h-8 bg-gradient-to-r from-blue-600 to-purple-600 rounded flex items-center justify-center text-white text-xs font-bold">
              VISA
            </div>
            <div className="flex-1">
              <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                •••• •••• •••• 4242
              </p>
              <p className="text-xs text-gray-600 dark:text-gray-400">Expires 12/2026</p>
            </div>
            <span className="px-2 py-1 bg-green-100 dark:bg-green-900/30 text-green-900 dark:text-green-200 text-xs font-semibold rounded">
              PRIMARY
            </span>
          </div>
        </div>

        {/* Billing History */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-4">
            Billing History
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-200 dark:border-gray-700">
                  <th className="text-left py-3 px-4 text-sm font-semibold text-gray-900 dark:text-gray-100">
                    Date
                  </th>
                  <th className="text-left py-3 px-4 text-sm font-semibold text-gray-900 dark:text-gray-100">
                    Plan
                  </th>
                  <th className="text-left py-3 px-4 text-sm font-semibold text-gray-900 dark:text-gray-100">
                    Amount
                  </th>
                  <th className="text-left py-3 px-4 text-sm font-semibold text-gray-900 dark:text-gray-100">
                    Status
                  </th>
                  <th className="text-left py-3 px-4 text-sm font-semibold text-gray-900 dark:text-gray-100">
                    Invoice
                  </th>
                </tr>
              </thead>
              <tbody>
                {BILLING_HISTORY.map((invoice) => (
                  <tr
                    key={invoice.id}
                    className="border-b border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-900/50"
                  >
                    <td className="py-3 px-4 text-sm text-gray-700 dark:text-gray-300">
                      {invoice.date}
                    </td>
                    <td className="py-3 px-4 text-sm text-gray-700 dark:text-gray-300">
                      {invoice.plan}
                    </td>
                    <td className="py-3 px-4 text-sm font-medium text-gray-900 dark:text-gray-100">
                      {invoice.amount}
                    </td>
                    <td className="py-3 px-4">
                      <span className="px-2 py-1 bg-green-100 dark:bg-green-900/30 text-green-900 dark:text-green-200 text-xs font-semibold rounded-full">
                        {invoice.status.toUpperCase()}
                      </span>
                    </td>
                    <td className="py-3 px-4">
                      <button className="text-sm text-blue-600 dark:text-blue-400 hover:underline">
                        Download
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}
