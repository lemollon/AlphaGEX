'use client'

import BotReportArchive from '@/components/trader/BotReportArchive'

export default function PegasusReportArchivePage() {
  return (
    <div className="min-h-screen bg-background p-6">
      <div className="max-w-6xl mx-auto">
        <BotReportArchive
          botName="PEGASUS"
          botDisplayName="PEGASUS"
          brandColor="blue"
          backLink="/pegasus"
        />
      </div>
    </div>
  )
}
