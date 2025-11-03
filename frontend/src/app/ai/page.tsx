'use client'

import { useState, useRef, useEffect } from 'react'
import { MessageSquare, Send, Sparkles, TrendingUp, BarChart3, Zap, Clock, User, Bot } from 'lucide-react'
import { apiClient } from '@/lib/api'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  analysis?: {
    sentiment: string
    confidence: number
    key_points: string[]
    recommendation: string
  }
}

export default function AICopilot() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      role: 'assistant',
      content: "Hi! I'm your AI trading copilot. I can analyze market conditions, explain gamma exposure, suggest trades, and answer any questions about options trading. How can I help you today?",
      timestamp: new Date()
    }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const quickPrompts = [
    { icon: TrendingUp, text: 'Analyze current SPY gamma exposure', category: 'analysis' },
    { icon: BarChart3, text: 'What are the key support/resistance levels?', category: 'levels' },
    { icon: Zap, text: 'Explain market maker hedging behavior', category: 'education' },
    { icon: Clock, text: 'What trades should I consider today?', category: 'strategy' }
  ]

  const handleSend = async () => {
    if (!input.trim() || loading) return

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input,
      timestamp: new Date()
    }

    setMessages(prev => [...prev, userMessage])
    setInput('')
    setLoading(true)

    try {
      // Call AI analysis endpoint
      const response = await apiClient.analyzeMarket({
        symbol: 'SPY',
        query: input,
        market_data: {},
        gamma_intel: {}
      })

      const aiMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: response.data.data.analysis,
        timestamp: new Date(),
        analysis: response.data.data.insights
      }

      setMessages(prev => [...prev, aiMessage])
    } catch (error) {
      console.error('Error getting AI response:', error)

      // Fallback response
      const aiMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: "I apologize, but I'm having trouble connecting to the analysis service right now. This is a simulated response. In production, I would provide detailed market analysis based on real-time gamma exposure data, market conditions, and trading patterns.",
        timestamp: new Date()
      }

      setMessages(prev => [...prev, aiMessage])
    } finally {
      setLoading(false)
    }
  }

  const handleQuickPrompt = (prompt: string) => {
    setInput(prompt)
  }

  const formatTime = (date: Date) => {
    return new Intl.DateTimeFormat('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      hour12: true
    }).format(date)
  }

  return (
    <div className="h-[calc(100vh-8rem)] flex flex-col">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-text-primary">AI Copilot</h1>
        <p className="text-text-secondary mt-1">Ask anything about market analysis, gamma exposure, or trading strategies</p>
      </div>

      {/* Chat Container */}
      <div className="flex-1 flex flex-col min-h-0 card">
        {/* Messages Area */}
        <div className="flex-1 overflow-y-auto space-y-4 p-4">
          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex gap-3 ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              {message.role === 'assistant' && (
                <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center">
                  <Bot className="w-5 h-5 text-primary" />
                </div>
              )}

              <div className={`flex-1 max-w-3xl ${message.role === 'user' ? 'flex justify-end' : ''}`}>
                <div
                  className={`rounded-lg p-4 ${
                    message.role === 'user'
                      ? 'bg-primary text-white'
                      : 'bg-background-hover text-text-primary'
                  }`}
                >
                  <p className="whitespace-pre-wrap">{message.content}</p>

                  {/* Analysis Card */}
                  {message.analysis && (
                    <div className="mt-4 pt-4 border-t border-border/30 space-y-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <Sparkles className="w-4 h-4" />
                          <span className="text-sm font-semibold">Analysis Insights</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-text-muted">Confidence:</span>
                          <span className="text-sm font-semibold text-success">
                            {message.analysis.confidence}%
                          </span>
                        </div>
                      </div>

                      <div>
                        <p className="text-xs text-text-muted uppercase mb-1">Sentiment</p>
                        <p className={`text-sm font-semibold ${
                          message.analysis.sentiment === 'Bullish' ? 'text-success' :
                          message.analysis.sentiment === 'Bearish' ? 'text-danger' :
                          'text-warning'
                        }`}>
                          {message.analysis.sentiment}
                        </p>
                      </div>

                      {message.analysis.key_points.length > 0 && (
                        <div>
                          <p className="text-xs text-text-muted uppercase mb-2">Key Points</p>
                          <ul className="space-y-1">
                            {message.analysis.key_points.map((point, idx) => (
                              <li key={idx} className="text-sm flex items-start gap-2">
                                <span className="text-primary mt-1">•</span>
                                <span>{point}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {message.analysis.recommendation && (
                        <div className="p-3 bg-primary/10 rounded-lg">
                          <p className="text-xs text-text-muted uppercase mb-1">Recommendation</p>
                          <p className="text-sm font-medium">{message.analysis.recommendation}</p>
                        </div>
                      )}
                    </div>
                  )}

                  <p className="text-xs opacity-60 mt-2">{formatTime(message.timestamp)}</p>
                </div>
              </div>

              {message.role === 'user' && (
                <div className="flex-shrink-0 w-8 h-8 rounded-full bg-background-hover flex items-center justify-center">
                  <User className="w-5 h-5 text-text-secondary" />
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div className="flex gap-3">
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center">
                <Bot className="w-5 h-5 text-primary" />
              </div>
              <div className="flex-1 max-w-3xl">
                <div className="bg-background-hover rounded-lg p-4">
                  <div className="flex gap-2">
                    <div className="w-2 h-2 bg-primary rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                    <div className="w-2 h-2 bg-primary rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                    <div className="w-2 h-2 bg-primary rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Quick Prompts */}
        {messages.length <= 1 && (
          <div className="p-4 border-t border-border">
            <p className="text-text-secondary text-sm mb-3">Try asking:</p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {quickPrompts.map((prompt, idx) => {
                const Icon = prompt.icon
                return (
                  <button
                    key={idx}
                    onClick={() => handleQuickPrompt(prompt.text)}
                    className="flex items-center gap-3 p-3 bg-background-hover hover:bg-background-hover/70 rounded-lg transition-all text-left group"
                  >
                    <Icon className="w-5 h-5 text-primary group-hover:scale-110 transition-transform" />
                    <span className="text-text-primary text-sm">{prompt.text}</span>
                  </button>
                )
              })}
            </div>
          </div>
        )}

        {/* Input Area */}
        <div className="p-4 border-t border-border">
          <div className="flex gap-3">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  handleSend()
                }
              }}
              placeholder="Ask about market conditions, gamma levels, trading strategies..."
              className="input flex-1"
              disabled={loading}
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || loading}
              className="btn-primary px-6 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              <Send className="w-4 h-4" />
              Send
            </button>
          </div>
          <p className="text-text-muted text-xs mt-2">
            Press Enter to send, Shift+Enter for new line
          </p>
        </div>
      </div>

      {/* Info Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-6">
        <div className="card bg-primary/5 border border-primary/20">
          <div className="flex items-start gap-3">
            <MessageSquare className="w-5 h-5 text-primary flex-shrink-0 mt-1" />
            <div>
              <h3 className="font-semibold text-text-primary mb-1">Market Analysis</h3>
              <p className="text-text-secondary text-sm">Get real-time insights on gamma exposure, support/resistance, and market dynamics</p>
            </div>
          </div>
        </div>

        <div className="card bg-success/5 border border-success/20">
          <div className="flex items-start gap-3">
            <Sparkles className="w-5 h-5 text-success flex-shrink-0 mt-1" />
            <div>
              <h3 className="font-semibold text-text-primary mb-1">Trade Ideas</h3>
              <p className="text-text-secondary text-sm">Receive actionable trade suggestions based on current market conditions</p>
            </div>
          </div>
        </div>

        <div className="card bg-warning/5 border border-warning/20">
          <div className="flex items-start gap-3">
            <Zap className="w-5 h-5 text-warning flex-shrink-0 mt-1" />
            <div>
              <h3 className="font-semibold text-text-primary mb-1">Education</h3>
              <p className="text-text-secondary text-sm">Learn about gamma, vanna, charm, and how market makers hedge positions</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
