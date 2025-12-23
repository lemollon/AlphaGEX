'use client'

import React, { useState } from 'react'
import { ChevronDown, ChevronUp, MessageSquare, Bot, Clock, Zap, AlertTriangle, ShieldAlert, CheckCircle, FileText } from 'lucide-react'

interface ClaudeConversationViewerProps {
  prompt: string
  response: string
  model?: string
  tokensUsed?: number
  responseTimeMs?: number
  chainName?: string
  confidence?: string
  warnings?: string[]
  className?: string
  // Anti-hallucination fields
  hallucinationRisk?: 'LOW' | 'MEDIUM' | 'HIGH'
  hallucinationWarnings?: string[]
  dataCitations?: string[]
}

export default function ClaudeConversationViewer({
  prompt,
  response,
  model = 'claude-sonnet-4-5-20250929',
  tokensUsed = 0,
  responseTimeMs = 0,
  chainName = '',
  confidence = '',
  warnings = [],
  className = '',
  hallucinationRisk = 'LOW',
  hallucinationWarnings = [],
  dataCitations = []
}: ClaudeConversationViewerProps) {
  const [isExpanded, setIsExpanded] = useState(false)
  const [showFullPrompt, setShowFullPrompt] = useState(false)
  const [showFullResponse, setShowFullResponse] = useState(false)

  const truncate = (text: string, maxLength: number) => {
    if (text.length <= maxLength) return text
    return text.substring(0, maxLength) + '...'
  }

  const hasContent = prompt || response

  if (!hasContent) {
    return (
      <div className={`bg-gray-800/50 rounded-lg p-4 border border-gray-700 ${className}`}>
        <div className="flex items-center gap-2 text-gray-500">
          <Bot className="w-5 h-5" />
          <span>No Claude AI interaction recorded for this decision</span>
        </div>
      </div>
    )
  }

  return (
    <div className={`bg-gray-800 rounded-lg border border-gray-700 overflow-hidden ${className}`}>
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-4 py-3 flex items-center justify-between bg-purple-900/30 hover:bg-purple-900/40 transition-colors"
      >
        <div className="flex items-center gap-3">
          <Bot className="w-5 h-5 text-purple-400" />
          <span className="font-medium text-purple-300">Claude AI Conversation</span>
          {model && (
            <span className="text-xs bg-purple-800/50 text-purple-300 px-2 py-0.5 rounded">
              {model}
            </span>
          )}
          {chainName && (
            <span className="text-xs bg-blue-800/50 text-blue-300 px-2 py-0.5 rounded">
              {chainName}
            </span>
          )}
        </div>
        <div className="flex items-center gap-4">
          {/* Stats */}
          {tokensUsed > 0 && (
            <div className="flex items-center gap-1 text-xs text-gray-400">
              <Zap className="w-3 h-3" />
              <span>{tokensUsed.toLocaleString()} tokens</span>
            </div>
          )}
          {responseTimeMs > 0 && (
            <div className="flex items-center gap-1 text-xs text-gray-400">
              <Clock className="w-3 h-3" />
              <span>{responseTimeMs}ms</span>
            </div>
          )}
          {confidence && (
            <span className={`text-xs px-2 py-0.5 rounded ${
              confidence === 'HIGH' ? 'bg-green-800/50 text-green-300' :
              confidence === 'MEDIUM' ? 'bg-yellow-800/50 text-yellow-300' :
              'bg-red-800/50 text-red-300'
            }`}>
              {confidence}
            </span>
          )}
          {/* Hallucination Risk Badge */}
          <span className={`text-xs px-2 py-0.5 rounded flex items-center gap-1 ${
            hallucinationRisk === 'LOW' ? 'bg-green-800/50 text-green-300' :
            hallucinationRisk === 'MEDIUM' ? 'bg-yellow-800/50 text-yellow-300' :
            'bg-red-800/50 text-red-300'
          }`}>
            {hallucinationRisk === 'LOW' ? (
              <CheckCircle className="w-3 h-3" />
            ) : (
              <ShieldAlert className="w-3 h-3" />
            )}
            <span>{hallucinationRisk === 'LOW' ? 'Verified' : hallucinationRisk === 'MEDIUM' ? 'Caution' : 'Risk'}</span>
          </span>
          {isExpanded ? (
            <ChevronUp className="w-5 h-5 text-gray-400" />
          ) : (
            <ChevronDown className="w-5 h-5 text-gray-400" />
          )}
        </div>
      </button>

      {/* Expanded Content */}
      {isExpanded && (
        <div className="p-4 space-y-4">
          {/* Hallucination Risk Alert */}
          {hallucinationRisk !== 'LOW' && (
            <div className={`border rounded-lg p-3 ${
              hallucinationRisk === 'HIGH'
                ? 'bg-red-900/20 border-red-700/50'
                : 'bg-yellow-900/20 border-yellow-700/50'
            }`}>
              <div className={`flex items-center gap-2 mb-2 ${
                hallucinationRisk === 'HIGH' ? 'text-red-400' : 'text-yellow-400'
              }`}>
                <ShieldAlert className="w-4 h-4" />
                <span className="font-medium text-sm">
                  {hallucinationRisk === 'HIGH' ? 'High Hallucination Risk' : 'Moderate Hallucination Risk'}
                </span>
              </div>
              <p className={`text-sm mb-2 ${
                hallucinationRisk === 'HIGH' ? 'text-red-300/80' : 'text-yellow-300/80'
              }`}>
                {hallucinationRisk === 'HIGH'
                  ? 'This response may contain fabricated information. Verify all claims against input data.'
                  : 'Some aspects of this response may not be fully grounded in input data.'}
              </p>
              {hallucinationWarnings && hallucinationWarnings.length > 0 && (
                <ul className={`text-sm list-disc list-inside space-y-1 ${
                  hallucinationRisk === 'HIGH' ? 'text-red-300/70' : 'text-yellow-300/70'
                }`}>
                  {hallucinationWarnings.map((warning, i) => (
                    <li key={i}>{warning}</li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* Data Citations - shown when LOW risk */}
          {hallucinationRisk === 'LOW' && dataCitations && dataCitations.length > 0 && (
            <div className="bg-green-900/20 border border-green-700/50 rounded-lg p-3">
              <div className="flex items-center gap-2 text-green-400 mb-2">
                <FileText className="w-4 h-4" />
                <span className="font-medium text-sm">Data Citations (Verified)</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {dataCitations.map((citation, i) => (
                  <span key={i} className="text-xs bg-green-800/30 text-green-300 px-2 py-1 rounded">
                    {citation}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Warnings */}
          {warnings && warnings.length > 0 && (
            <div className="bg-yellow-900/20 border border-yellow-700/50 rounded-lg p-3">
              <div className="flex items-center gap-2 text-yellow-400 mb-2">
                <AlertTriangle className="w-4 h-4" />
                <span className="font-medium text-sm">AI Warnings</span>
              </div>
              <ul className="text-sm text-yellow-300/80 list-disc list-inside space-y-1">
                {warnings.map((warning, i) => (
                  <li key={i}>{warning}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Prompt Section */}
          {prompt && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm font-medium text-blue-400">
                  <MessageSquare className="w-4 h-4" />
                  <span>Prompt Sent to Claude</span>
                </div>
                {prompt.length > 500 && (
                  <button
                    onClick={() => setShowFullPrompt(!showFullPrompt)}
                    className="text-xs text-blue-400 hover:text-blue-300"
                  >
                    {showFullPrompt ? 'Show less' : 'Show full prompt'}
                  </button>
                )}
              </div>
              <div className="bg-gray-900 rounded-lg p-3 border border-gray-700">
                <pre className="text-sm text-gray-300 whitespace-pre-wrap font-mono">
                  {showFullPrompt ? prompt : truncate(prompt, 500)}
                </pre>
              </div>
            </div>
          )}

          {/* Response Section */}
          {response && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm font-medium text-purple-400">
                  <Bot className="w-4 h-4" />
                  <span>Claude&apos;s Response</span>
                </div>
                {response.length > 500 && (
                  <button
                    onClick={() => setShowFullResponse(!showFullResponse)}
                    className="text-xs text-purple-400 hover:text-purple-300"
                  >
                    {showFullResponse ? 'Show less' : 'Show full response'}
                  </button>
                )}
              </div>
              <div className="bg-purple-900/20 rounded-lg p-3 border border-purple-700/50">
                <pre className="text-sm text-gray-300 whitespace-pre-wrap font-mono">
                  {showFullResponse ? response : truncate(response, 500)}
                </pre>
              </div>
            </div>
          )}

          {/* Metadata */}
          <div className="flex flex-wrap gap-4 text-xs text-gray-500 pt-2 border-t border-gray-700">
            {model && <span>Model: {model}</span>}
            {chainName && <span>Chain: {chainName}</span>}
            {tokensUsed > 0 && <span>Tokens: {tokensUsed.toLocaleString()}</span>}
            {responseTimeMs > 0 && <span>Response time: {responseTimeMs}ms</span>}
          </div>
        </div>
      )}
    </div>
  )
}
