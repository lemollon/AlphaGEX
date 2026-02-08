'use client'

import CovenantLoadingScreen from '@/components/CovenantLoadingScreen'

export default function Loading() {
  return (
    <CovenantLoadingScreen
      message="Initializing AlphaGEX"
      subMessage="Connecting COVENANT neural pathways..."
      showTips={true}
    />
  )
}
