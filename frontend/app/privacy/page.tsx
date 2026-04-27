export const metadata = {
  title: 'Privacy Policy — Tsushin',
  description: 'Privacy policy for the Tsushin platform.',
}

export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-tsushin-ink text-gray-200 px-6 py-16 max-w-3xl mx-auto font-sans">
      <h1 className="text-3xl font-bold text-white mb-2">Privacy Policy</h1>
      <p className="text-sm text-gray-400 mb-10">Last updated: February 14, 2026</p>

      <section className="mb-8">
        <h2 className="text-xl font-semibold text-white mb-3">1. What We Collect</h2>
        <p className="text-gray-300 leading-relaxed">
          When you connect a Google account to Tsushin, we request access to the following data
          depending on the integrations you enable:
        </p>
        <ul className="list-disc list-inside mt-3 space-y-1 text-gray-300">
          <li><strong className="text-white">Email address</strong> — to identify your connected account.</li>
          <li><strong className="text-white">Google Calendar events</strong> — to read and manage calendar events on your behalf (Calendar integration).</li>
          <li><strong className="text-white">Gmail messages</strong> — read-only access to retrieve email content (Gmail integration).</li>
        </ul>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold text-white mb-3">2. How We Use Your Data</h2>
        <p className="text-gray-300 leading-relaxed">
          Your data is used exclusively to power the integrations you configure within the Tsushin
          platform. For example, listing upcoming calendar events, reading recent emails, or
          scheduling meetings through your AI agents. We do not use your data for advertising,
          profiling, or any purpose other than the functionality you explicitly enable.
        </p>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold text-white mb-3">3. Data Storage &amp; Security</h2>
        <ul className="list-disc list-inside space-y-1 text-gray-300">
          <li>All OAuth tokens (access and refresh tokens) are encrypted at rest using Fernet (AES-128 + HMAC) with per-tenant key derivation.</li>
          <li>Each tenant&apos;s data is isolated — one organization cannot access another&apos;s tokens or data.</li>
          <li>We do not store the content of your emails or calendar events beyond transient processing to fulfill your requests.</li>
        </ul>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold text-white mb-3">4. Data Sharing</h2>
        <p className="text-gray-300 leading-relaxed">
          We do not sell, rent, or share your personal data or Google account data with any third
          parties. Your data remains within your Tsushin workspace.
        </p>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold text-white mb-3">5. Revoking Access</h2>
        <p className="text-gray-300 leading-relaxed">
          You can disconnect any Google integration at any time from the Tsushin Hub page. You can
          also revoke Tsushin&apos;s access directly from your{' '}
          <a
            href="https://myaccount.google.com/permissions"
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-400 hover:text-blue-300 underline"
          >
            Google Account permissions page
          </a>
          . When access is revoked, all stored tokens for that integration are deleted.
        </p>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold text-white mb-3">6. Contact</h2>
        <p className="text-gray-300 leading-relaxed">
          For privacy-related inquiries, contact us at{' '}
          <a href="mailto:privacy@archsec.io" className="text-blue-400 hover:text-blue-300 underline">
            privacy@archsec.io
          </a>.
        </p>
      </section>
    </div>
  )
}
