'use client'

import NexusLoadingScreen from '@/components/NexusLoadingScreen'

export default function Loading() {
  return (
    <NexusLoadingScreen
      message="Initializing AlphaGEX"
      subMessage="Connecting NEXUS neural pathways..."
      showTips={true}
    />
  )
}
