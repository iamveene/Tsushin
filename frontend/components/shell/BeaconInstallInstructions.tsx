'use client'

import CopyableBlock from '@/components/ui/CopyableBlock'

interface Props {
  apiKey: string
  apiBaseUrl?: string
  onCopyFeedback?: (msg: string) => void
}

/**
 * Shared block rendering the three beacon install options.
 * Extracted from frontend/app/hub/shell/page.tsx so both the existing
 * "bare form" modal and the new ShellBeaconSetupWizard render the same
 * install guidance with the same source of truth.
 */
export default function BeaconInstallInstructions({
  apiKey,
  apiBaseUrl = '',
  onCopyFeedback,
}: Props) {
  const downloadUrl = `${apiBaseUrl}/api/shell/beacon/download`
  const serverUrl = `${apiBaseUrl}/api/shell`

  const installScript = `# Download and install beacon
curl -L -H "X-API-Key: ${apiKey}" "${downloadUrl}" -o beacon.zip && \\
unzip beacon.zip && \\
cd shell_beacon && \\
pip install -r requirements.txt

# Run beacon with auto-start persistence (survives reboots)
python run.py \\
  --server "${serverUrl}" \\
  --api-key "${apiKey}" \\
  --persistence install`

  const runOnly = `# From INSIDE shell_beacon/ directory (with persistence)
cd shell_beacon
python run.py --server "${serverUrl}" --api-key "${apiKey}" --persistence install

# OR without persistence (manual start required after reboot)
python run.py --server "${serverUrl}" --api-key "${apiKey}"

# Persistence management commands:
python run.py --persistence status    # Check if persistence is installed
python run.py --persistence uninstall # Remove auto-start`

  const yaml = `# Tsushin Beacon Configuration
server:
  url: "${serverUrl}"
  api_key: "${apiKey}"

connection:
  poll_interval: 5
  reconnect_delay: 5
  max_reconnect_delay: 300

execution:
  shell: "/bin/bash"
  timeout: 300

logging:
  level: "INFO"
  file: "~/.tsushin/beacon.log"`

  return (
    <div className="space-y-4">
      <div className="bg-gray-800 p-4 rounded-lg">
        <div className="flex justify-between items-center mb-2">
          <p className="text-sm text-gray-400">API Key (save this — shown only once!)</p>
          <button
            onClick={() => {
              navigator.clipboard?.writeText(apiKey)
              onCopyFeedback?.('API key copied!')
            }}
            className="text-xs px-2 py-1 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded"
          >
            Copy
          </button>
        </div>
        <code className="text-teal-400 font-mono text-sm break-all select-all">{apiKey}</code>
      </div>

      <div className="border border-gray-700 rounded-lg p-4">
        <h3 className="text-base font-semibold text-white mb-3">Installation</h3>

        <div className="mb-4">
          <p className="text-sm text-gray-400 mb-2">Option 1 — Download the beacon package</p>
          <a
            href={downloadUrl}
            className="inline-flex items-center gap-2 px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-lg text-sm"
          >
            Download Beacon Package
          </a>
        </div>

        <div className="mb-4">
          <p className="text-sm text-gray-400 mb-2">Option 2 — Quick install (paste into the target terminal)</p>
          <CopyableBlock value={installScript} tone="teal" maxHeight="16rem" />
        </div>

        <div className="mb-2">
          <p className="text-sm text-gray-400 mb-2">Option 3 — Already installed? just run it</p>
          <CopyableBlock value={runOnly} tone="teal" maxHeight="14rem" />
          <p className="text-xs text-teal-400 mt-2">
            <code>--persistence install</code> auto-starts the beacon on login/reboot
            (Linux: systemd, macOS: LaunchAgent, Windows: Task Scheduler).
          </p>
        </div>
      </div>

      <details className="border border-gray-700 rounded-lg p-4">
        <summary className="text-sm font-medium text-gray-300 cursor-pointer hover:text-white">
          Advanced — use a config file (beacon.yaml)
        </summary>
        <div className="mt-3">
          <p className="text-xs text-gray-400 mb-2">
            Save this as <code className="text-teal-400">~/.tsushin/beacon.yaml</code>:
          </p>
          <CopyableBlock value={yaml} tone="amber" maxHeight="18rem" />
          <p className="text-xs text-gray-500 mt-2">
            Then run: <code className="text-teal-400">python -m shell_beacon</code>
          </p>
        </div>
      </details>
    </div>
  )
}
