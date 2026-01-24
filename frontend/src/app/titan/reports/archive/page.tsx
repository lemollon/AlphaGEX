'use client'

import BotReportArchive from '@/components/trader/BotReportArchive'

export default function TitanReportArchivePage() {
  return (
    <div className="min-h-screen bg-background p-6">
      <div className="max-w-6xl mx-auto">
        <BotReportArchive
          botName="TITAN"
          botDisplayName="TITAN"
          brandColor="violet"
          backLink="/titan"
        />
      </div>
    </div>
  )
}
