'use client'

import { useState } from 'react'
import CovenantLoadingScreen from '@/components/CovenantLoadingScreen'
import CovenantCanvas, { BotStatus } from '@/components/CovenantCanvas'

export default function CovenantDemoPage() {
  const [showFullScreen, setShowFullScreen] = useState(false)
  const [progress, setProgress] = useState(0)
  const [botStatus, setBotStatus] = useState<BotStatus>({
    gex: 'active',
    prophet: 'active',
    fortress: 'idle',
    solomon: 'trading',
    lazarus: 'idle',
    cornerstone: 'idle',
  })

  const handleNodeClick = (nodeId: string) => {
    console.log('Clicked node:', nodeId)
    // Toggle status for demo
    setBotStatus(prev => ({
      ...prev,
      [nodeId === 'gex-core' ? 'gex' : nodeId]:
        prev[nodeId === 'gex-core' ? 'gex' : nodeId as keyof BotStatus] === 'active'
          ? 'trading'
          : prev[nodeId === 'gex-core' ? 'gex' : nodeId as keyof BotStatus] === 'trading'
          ? 'idle'
          : 'active'
    }))
  }

  const simulateProgress = () => {
    setProgress(0)
    const interval = setInterval(() => {
      setProgress(prev => {
        if (prev >= 100) {
          clearInterval(interval)
          return 100
        }
        return prev + Math.random() * 15
      })
    }, 500)
  }

  if (showFullScreen) {
    return (
      <CovenantLoadingScreen
        message="AlphaGEX COVENANT"
        subMessage="Click nodes to change their status. Press ESC to exit."
        showProgress={progress > 0}
        progress={progress}
        botStatus={botStatus}
        onNodeClick={handleNodeClick}
        showTips={true}
      />
    )
  }

  return (
    <div className="min-h-screen bg-background-deep p-8">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-text-primary mb-2">
            COVENANT Animation Demo
          </h1>
          <p className="text-text-secondary">
            Interactive preview of the AlphaGEX COVENANT neural network interface
          </p>
        </div>

        {/* Controls */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          {/* Actions */}
          <div className="bg-background-card rounded-xl p-6 border border-gray-700">
            <h2 className="text-lg font-semibold text-text-primary mb-4">Actions</h2>
            <div className="space-y-3">
              <button
                onClick={() => setShowFullScreen(true)}
                className="w-full px-4 py-3 bg-primary hover:bg-primary-hover text-white rounded-lg font-medium transition-colors"
              >
                View Full Screen Loading
              </button>
              <button
                onClick={simulateProgress}
                className="w-full px-4 py-3 bg-background-hover hover:bg-gray-700 text-text-primary rounded-lg font-medium transition-colors border border-gray-600"
              >
                Simulate Progress
              </button>
            </div>
          </div>

          {/* Bot Status Controls */}
          <div className="bg-background-card rounded-xl p-6 border border-gray-700">
            <h2 className="text-lg font-semibold text-text-primary mb-4">Bot Status</h2>
            <div className="grid grid-cols-2 gap-3">
              {Object.entries(botStatus).map(([bot, status]) => (
                <button
                  key={bot}
                  onClick={() => {
                    const statuses: Array<BotStatus[keyof BotStatus]> = ['active', 'idle', 'trading', 'error']
                    const currentIdx = statuses.indexOf(status)
                    const nextIdx = (currentIdx + 1) % statuses.length
                    setBotStatus(prev => ({ ...prev, [bot]: statuses[nextIdx] }))
                  }}
                  className="flex items-center justify-between px-3 py-2 bg-background-deep rounded-lg border border-gray-600 hover:border-gray-500 transition-colors"
                >
                  <span className="text-text-primary text-sm font-medium uppercase">{bot}</span>
                  <span className={`text-xs px-2 py-0.5 rounded ${
                    status === 'active' ? 'bg-success/20 text-success' :
                    status === 'trading' ? 'bg-warning/20 text-warning' :
                    status === 'error' ? 'bg-danger/20 text-danger' :
                    'bg-gray-600/20 text-gray-400'
                  }`}>
                    {status}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Embedded Preview */}
        <div className="bg-background-card rounded-xl border border-gray-700 overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-700 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-text-primary">COVENANT Live Preview</h2>
            <span className="text-xs text-text-muted">Click nodes to interact</span>
          </div>
          <div className="h-[500px] relative">
            <CovenantCanvas
              botStatus={botStatus}
              onNodeClick={handleNodeClick}
              showLabels={true}
            />
          </div>
        </div>

        {/* Feature List */}
        <div className="mt-8 bg-background-card rounded-xl p-6 border border-gray-700">
          <h2 className="text-lg font-semibold text-text-primary mb-4">COVENANT Features</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[
              { title: 'Central GEX Core', desc: 'Pulsing orb with rotating rings' },
              { title: 'Neural Fibers', desc: 'Organic connections with bezier curves' },
              { title: 'Particle Pulses', desc: 'Data signals flowing between nodes' },
              { title: 'Bot Nodes', desc: 'PROPHET, FORTRESS, SOLOMON, LAZARUS, CORNERSTONE' },
              { title: 'Status Indicators', desc: 'Active, Idle, Trading, Error states' },
              { title: 'Interactive Hover', desc: 'Highlight and tooltip on hover' },
              { title: 'Full Responsive', desc: 'Scales to any viewport size' },
              { title: 'Pro Tips', desc: 'Rotating trading tips at bottom' },
              { title: 'Progress Bar', desc: 'Optional loading progress indicator' },
            ].map(feature => (
              <div key={feature.title} className="bg-background-deep rounded-lg p-4">
                <h3 className="text-text-primary font-medium text-sm">{feature.title}</h3>
                <p className="text-text-muted text-xs mt-1">{feature.desc}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Usage Code */}
        <div className="mt-8 bg-background-card rounded-xl p-6 border border-gray-700">
          <h2 className="text-lg font-semibold text-text-primary mb-4">Usage</h2>
          <pre className="bg-background-deep rounded-lg p-4 overflow-x-auto text-sm">
            <code className="text-text-secondary">
{`// Full page loading screen
import CovenantLoadingScreen from '@/components/CovenantLoadingScreen'

<CovenantLoadingScreen
  message="Loading..."
  subMessage="Please wait..."
  showProgress={true}
  progress={50}
  botStatus={{
    gex: 'active',
    prophet: 'active',
    fortress: 'trading',
    solomon: 'idle',
  }}
  onNodeClick={(nodeId) => console.log(nodeId)}
/>

// Just the canvas (embeddable)
import CovenantCanvas from '@/components/CovenantCanvas'

<div className="h-[400px]">
  <CovenantCanvas
    botStatus={botStatus}
    onNodeClick={handleNodeClick}
    showLabels={true}
  />
</div>`}
            </code>
          </pre>
        </div>
      </div>
    </div>
  )
}
