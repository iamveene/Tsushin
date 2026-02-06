import './globals.css'
import { DM_Sans, Plus_Jakarta_Sans, JetBrains_Mono } from 'next/font/google'
import { AuthProvider } from '@/contexts/AuthContext'
import { OnboardingProvider } from '@/contexts/OnboardingContext'
import LayoutContent from '@/components/LayoutContent'
import OnboardingWizard from '@/components/OnboardingWizard'

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

export const metadata = {
  title: 'Tsushin Beta — The Agentic Framework',
  description: 'Orchestrate conversations. Automate outcomes.',
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
            <LayoutContent>{children}</LayoutContent>
            <OnboardingWizard />
          </OnboardingProvider>
        </AuthProvider>
      </body>
    </html>
  )
}
