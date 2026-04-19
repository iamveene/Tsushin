import './globals.css'
import type { Metadata } from 'next'
import { DM_Sans, Plus_Jakarta_Sans, JetBrains_Mono } from 'next/font/google'
import { AuthProvider } from '@/contexts/AuthContext'
import { OnboardingProvider } from '@/contexts/OnboardingContext'
import { WhatsAppWizardProvider } from '@/contexts/WhatsAppWizardContext'
import { GoogleWizardProvider } from '@/contexts/GoogleWizardContext'
import { ToastProvider } from '@/contexts/ToastContext'
import LayoutContent from '@/components/LayoutContent'
import OnboardingWizard from '@/components/OnboardingWizard'
import WhatsAppSetupWizard from '@/components/whatsapp-wizard/WhatsAppSetupWizard'
import ToastContainer from '@/components/ui/ToastContainer'
import PlaygroundMini from '@/components/playground/mini/PlaygroundMini'

// Primary body font - clean and modern
const dmSans = DM_Sans({
  subsets: ['latin'],
  variable: '--font-dm-sans',
  display: 'swap',
})

// Display font for headings - distinctive and bold
const plusJakartaSans = Plus_Jakarta_Sans({
  subsets: ['latin'],
  variable: '--font-jakarta',
  display: 'swap',
})

// Monospace font for code and technical elements
const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  variable: '--font-mono',
  display: 'swap',
})

export const metadata: Metadata = {
  title: 'Tsushin Beta — Think, Secure, Build',
  description: 'Orchestrate conversations. Automate outcomes.',
  icons: {
    icon: [
      { url: '/favicon.ico', sizes: '16x16', type: 'image/x-icon' },
    ],
    shortcut: '/favicon.ico',
    apple: '/favicon.ico',
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className="dark">
      <body className={`${dmSans.variable} ${plusJakartaSans.variable} ${jetbrainsMono.variable} font-sans bg-tsushin-ink text-gray-100 antialiased`}>
        <AuthProvider>
          <OnboardingProvider>
            <WhatsAppWizardProvider>
              <GoogleWizardProvider>
                <ToastProvider>
                  <LayoutContent>{children}</LayoutContent>
                  <OnboardingWizard />
                  <WhatsAppSetupWizard />
                  <PlaygroundMini />
                  <ToastContainer />
                </ToastProvider>
              </GoogleWizardProvider>
            </WhatsAppWizardProvider>
          </OnboardingProvider>
        </AuthProvider>
      </body>
    </html>
  )
}
