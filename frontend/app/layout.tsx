import './globals.css'
import type { Metadata } from 'next'
import { AuthProvider } from '@/contexts/AuthContext'
import { OnboardingProvider } from '@/contexts/OnboardingContext'
import { WhatsAppWizardProvider } from '@/contexts/WhatsAppWizardContext'
import { GoogleWizardProvider } from '@/contexts/GoogleWizardContext'
import { AudioWizardProvider } from '@/contexts/AudioWizardContext'
import { AgentWizardProvider } from '@/contexts/AgentWizardContext'
import { TeamWizardProvider } from '@/contexts/TeamWizardContext'
import { RepositoryAutomationWizardProvider } from '@/contexts/RepositoryAutomationWizardContext'
import { ProviderWizardProvider } from '@/contexts/ProviderWizardContext'
import { ToastProvider } from '@/contexts/ToastContext'
import LayoutContent from '@/components/LayoutContent'
import OnboardingWizard from '@/components/OnboardingWizard'
import WhatsAppSetupWizard from '@/components/whatsapp-wizard/WhatsAppSetupWizard'
import ToastContainer from '@/components/ui/ToastContainer'
import PlaygroundMini from '@/components/playground/mini/PlaygroundMini'

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
      <body className="font-sans bg-tsushin-ink text-gray-100 antialiased">
        <AuthProvider>
          <OnboardingProvider>
            <WhatsAppWizardProvider>
              <GoogleWizardProvider>
                <AudioWizardProvider>
                  <AgentWizardProvider>
                    <TeamWizardProvider>
                      <RepositoryAutomationWizardProvider>
                        <ProviderWizardProvider>
                          <ToastProvider>
                            <LayoutContent>{children}</LayoutContent>
                            <OnboardingWizard />
                            <WhatsAppSetupWizard />
                            <PlaygroundMini />
                            <ToastContainer />
                          </ToastProvider>
                        </ProviderWizardProvider>
                      </RepositoryAutomationWizardProvider>
                    </TeamWizardProvider>
                  </AgentWizardProvider>
                </AudioWizardProvider>
              </GoogleWizardProvider>
            </WhatsAppWizardProvider>
          </OnboardingProvider>
        </AuthProvider>
      </body>
    </html>
  )
}
