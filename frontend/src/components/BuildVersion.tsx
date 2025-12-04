'use client'

/**
 * BuildVersion Component
 * Shows the build timestamp and git commit in the UI
 * This helps verify that deployments went through correctly
 */
export default function BuildVersion() {
  const buildTime = process.env.NEXT_PUBLIC_BUILD_TIME || 'unknown'
  const buildCommit = process.env.NEXT_PUBLIC_BUILD_COMMIT || 'unknown'

  return (
    <div className="px-3 py-2 text-xs text-text-muted border-t border-gray-800 mt-4">
      <div className="flex items-center justify-between">
        <span>Build:</span>
        <span className="font-mono">{buildCommit}</span>
      </div>
      <div className="flex items-center justify-between mt-1">
        <span>Deployed:</span>
        <span className="font-mono">{buildTime}</span>
      </div>
    </div>
  )
}
