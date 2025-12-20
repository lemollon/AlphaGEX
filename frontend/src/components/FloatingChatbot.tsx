'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
import { Send, X, Minimize2, Maximize2, Image, Trash2, User, Loader2, Bot, Download, Volume2, VolumeX, Sparkles, Terminal, AlertTriangle } from 'lucide-react'
import { apiClient } from '@/lib/api'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  imageUrl?: string // Base64 image data URL
  type?: 'normal' | 'command' | 'briefing' | 'alert' // Message type for styling
}

// GEXIS Configuration
const GEXIS_NAME = 'GEXIS'
const GEXIS_FULL_NAME = 'Gamma Exposure eXpert Intelligence System'
const USER_NAME = 'Optionist Prime'

const STORAGE_KEY = 'alphagex_chat_history'
const SESSION_KEY = 'alphagex_session_id'
const SOUND_PREF_KEY = 'alphagex_sound_enabled'
const MAX_STORED_MESSAGES = 50

// Quick commands
const QUICK_COMMANDS = [
  { cmd: '/help', desc: 'Show available commands' },
  { cmd: '/status', desc: 'System & bot status' },
  { cmd: '/gex', desc: 'GEX data (e.g., /gex SPY)' },
  { cmd: '/positions', desc: 'Open positions' },
  { cmd: '/pnl', desc: 'P&L summary' },
  { cmd: '/briefing', desc: 'Daily market briefing' },
  { cmd: '/alerts', desc: 'Active alerts' },
]

// Known stock symbols for extraction
const KNOWN_SYMBOLS = new Set([
  'SPY', 'QQQ', 'IWM', 'DIA', 'SPX', 'NDX', 'VIX', 'UVXY', 'SQQQ', 'TQQQ',
  'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'META', 'NVDA', 'TSLA', 'AMD', 'NFLX',
  'JPM', 'BAC', 'GS', 'MS', 'WFC', 'C', 'V', 'MA', 'PYPL', 'SQ',
  'XOM', 'CVX', 'COP', 'OXY', 'SLB', 'HAL', 'MPC', 'VLO', 'PSX',
  'JNJ', 'PFE', 'UNH', 'ABBV', 'MRK', 'LLY', 'BMY', 'AMGN', 'GILD',
  'HD', 'LOW', 'TGT', 'WMT', 'COST', 'NKE', 'SBUX', 'MCD', 'DIS',
  'BA', 'CAT', 'GE', 'MMM', 'HON', 'UPS', 'FDX', 'LMT', 'RTX',
  'CRM', 'ORCL', 'IBM', 'INTC', 'CSCO', 'ADBE', 'NOW', 'SNOW', 'PLTR',
  'BTC', 'ETH', 'COIN', 'MSTR', 'RIOT', 'MARA', 'BITF', 'HUT',
  'GME', 'AMC', 'BBBY', 'BB', 'NOK', 'SOFI', 'HOOD', 'RIVN', 'LCID'
])

// Generate session ID
function generateSessionId(): string {
  return Math.random().toString(36).substring(2, 10)
}

// Extract symbol from user query
function extractSymbolFromQuery(query: string): string {
  const upperQuery = query.toUpperCase()

  // Look for $SYMBOL pattern first (e.g., "$AAPL")
  const dollarMatch = upperQuery.match(/\$([A-Z]{1,5})/)
  if (dollarMatch && KNOWN_SYMBOLS.has(dollarMatch[1])) {
    return dollarMatch[1]
  }

  // Look for known symbols in the query
  for (const symbol of KNOWN_SYMBOLS) {
    // Match whole word only (not part of another word)
    const regex = new RegExp(`\\b${symbol}\\b`)
    if (regex.test(upperQuery)) {
      return symbol
    }
  }

  // Default to SPY
  return 'SPY'
}

// Get time-based greeting for GEXIS
function getTimeGreeting(): string {
  const hour = new Date().getHours()
  if (hour >= 5 && hour < 12) return 'Good morning'
  if (hour >= 12 && hour < 17) return 'Good afternoon'
  return 'Good evening'
}

// Get GEXIS welcome message
function getGexisWelcomeMessage(): string {
  const greeting = getTimeGreeting()
  return `${greeting}, ${USER_NAME}. GEXIS online and at your service.

All systems are operational. I have full access to AlphaGEX's trading intelligence, including real-time GEX analysis, bot status monitoring, trade recommendations, and your trading history.

Quick Commands:
Type /help for available commands, or ask me anything naturally.

How may I assist you today?`
}

// Get GEXIS chat cleared message
function getGexisClearMessage(): string {
  return `Chat cleared, ${USER_NAME}. Ready for a fresh conversation. What shall we analyze?`
}

// Play notification sound
function playNotificationSound() {
  try {
    // Create a simple beep sound using Web Audio API
    const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)()
    const oscillator = audioContext.createOscillator()
    const gainNode = audioContext.createGain()

    oscillator.connect(gainNode)
    gainNode.connect(audioContext.destination)

    oscillator.frequency.value = 800
    oscillator.type = 'sine'
    gainNode.gain.setValueAtTime(0.1, audioContext.currentTime)
    gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.2)

    oscillator.start(audioContext.currentTime)
    oscillator.stop(audioContext.currentTime + 0.2)
  } catch (e) {
    // Silently fail if audio not supported
  }
}

export default function FloatingChatbot() {
  const [isOpen, setIsOpen] = useState(false)
  const [isMinimized, setIsMinimized] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [selectedImage, setSelectedImage] = useState<string | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [sessionId, setSessionId] = useState<string>('')
  const [soundEnabled, setSoundEnabled] = useState(true)
  const [showCommands, setShowCommands] = useState(false)
  const [alertCount, setAlertCount] = useState(0)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Initialize session ID
  useEffect(() => {
    let storedSession = localStorage.getItem(SESSION_KEY)
    if (!storedSession) {
      storedSession = generateSessionId()
      localStorage.setItem(SESSION_KEY, storedSession)
    }
    setSessionId(storedSession)
  }, [])

  // Load sound preference
  useEffect(() => {
    const pref = localStorage.getItem(SOUND_PREF_KEY)
    if (pref !== null) {
      setSoundEnabled(pref === 'true')
    }
  }, [])

  // Load messages from localStorage on mount
  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      if (stored) {
        const parsed = JSON.parse(stored)
        // Convert timestamp strings back to Date objects
        const messagesWithDates = parsed.map((m: any) => ({
          ...m,
          timestamp: new Date(m.timestamp)
        }))
        setMessages(messagesWithDates)
      } else {
        // Add GEXIS welcome message if no history
        setMessages([{
          id: '1',
          role: 'assistant',
          content: getGexisWelcomeMessage(),
          timestamp: new Date()
        }])
      }
    } catch (e) {
      console.error('Failed to load chat history:', e)
    }
  }, [])

  // Check for alerts periodically
  useEffect(() => {
    const checkAlerts = async () => {
      try {
        const response = await apiClient.gexisAlerts()
        const data = response.data
        if (data.success && data.count > 0) {
          setAlertCount(data.count)
        } else {
          setAlertCount(0)
        }
      } catch (e) {
        // Silently fail
      }
    }

    checkAlerts()
    const interval = setInterval(checkAlerts, 60000) // Check every minute
    return () => clearInterval(interval)
  }, [])

  // Save messages to localStorage whenever they change
  useEffect(() => {
    if (messages.length > 0) {
      try {
        // Only store the last N messages to avoid localStorage limits
        const toStore = messages.slice(-MAX_STORED_MESSAGES)
        localStorage.setItem(STORAGE_KEY, JSON.stringify(toStore))
      } catch (e) {
        console.error('Failed to save chat history:', e)
      }
    }
  }, [messages])

  // Scroll to bottom when messages change
  useEffect(() => {
    if (isOpen && !isMinimized) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages, isOpen, isMinimized])

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 120) + 'px'
    }
  }, [input])

  // Show command suggestions when typing /
  useEffect(() => {
    setShowCommands(input.startsWith('/') && !input.includes(' '))
  }, [input])

  const toggleSound = () => {
    const newValue = !soundEnabled
    setSoundEnabled(newValue)
    localStorage.setItem(SOUND_PREF_KEY, String(newValue))
  }

  const handleImageSelect = useCallback((file: File) => {
    if (!file.type.startsWith('image/')) {
      return
    }

    const reader = new FileReader()
    reader.onload = (e) => {
      setSelectedImage(e.target?.result as string)
    }
    reader.readAsDataURL(file)
  }, [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)

    const file = e.dataTransfer.files[0]
    if (file) {
      handleImageSelect(file)
    }
  }, [handleImageSelect])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
  }, [])

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      handleImageSelect(file)
    }
  }

  const clearImage = () => {
    setSelectedImage(null)
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  // Handle quick commands
  const handleCommand = async (command: string): Promise<string | null> => {
    try {
      const response = await apiClient.gexisCommand(command)
      const data = response.data

      if (data.success) {
        return data.response || data.briefing || 'Command executed successfully.'
      } else {
        return data.error || 'Command failed.'
      }
    } catch (e) {
      return 'Failed to execute command. Please try again.'
    }
  }

  const handleSend = async () => {
    if ((!input.trim() && !selectedImage) || loading) return

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input || (selectedImage ? '[Image uploaded for analysis]' : ''),
      timestamp: new Date(),
      imageUrl: selectedImage || undefined,
      type: input.startsWith('/') ? 'command' : 'normal'
    }

    setMessages(prev => [...prev, userMessage])
    const currentInput = input
    const currentImage = selectedImage
    setInput('')
    setSelectedImage(null)
    setShowCommands(false)
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
    setLoading(true)

    try {
      let response
      let analysisText = ''
      let messageType: 'normal' | 'command' | 'briefing' | 'alert' = 'normal'

      // Check if it's a quick command
      if (currentInput.trim().startsWith('/')) {
        const commandResult = await handleCommand(currentInput.trim())
        analysisText = commandResult || 'Command processed.'
        messageType = currentInput.includes('briefing') ? 'briefing' :
                      currentInput.includes('alert') ? 'alert' : 'command'
      } else {
        // Extract symbol from user query (or default to SPY)
        const detectedSymbol = extractSymbolFromQuery(currentInput)

        if (currentImage) {
          // Use image analysis endpoint
          response = await apiClient.analyzeWithImage({
            symbol: detectedSymbol,
            query: currentInput || 'Please analyze this image and provide trading insights.',
            image_data: currentImage
          })
        } else {
          // Use analysis with context endpoint for conversation memory
          response = await apiClient.gexisAnalyzeWithContext({
            query: currentInput,
            symbol: detectedSymbol,
            session_id: sessionId,
            market_data: {}
          })
          const data = response.data

          if (data.success && data.data) {
            analysisText = data.data.analysis || ''
          } else if (data.error) {
            throw new Error(data.error)
          }
        }

        // Handle API client response format
        if (response && 'data' in response) {
          const responseData = response.data
          if (responseData?.success && responseData?.data) {
            analysisText = responseData.data.analysis || responseData.data.response || ''
          } else if (responseData?.response) {
            analysisText = responseData.response
          } else if (responseData?.analysis) {
            analysisText = responseData.analysis
          }
        }
      }

      if (analysisText) {
        const aiMessage: Message = {
          id: (Date.now() + 1).toString(),
          role: 'assistant',
          content: analysisText,
          timestamp: new Date(),
          type: messageType
        }
        setMessages(prev => [...prev, aiMessage])

        // Play notification sound
        if (soundEnabled) {
          playNotificationSound()
        }
      } else {
        throw new Error('No analysis in response')
      }
    } catch (error: any) {
      console.error('Error getting AI response:', error)

      // Extract meaningful error message
      let errorMsg = 'Failed to get response'
      if (error?.response?.data?.detail) {
        errorMsg = error.response.data.detail
      } else if (error?.message) {
        errorMsg = error.message
      }

      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: `I apologize, ${USER_NAME}. I've encountered an issue: ${errorMsg}\n\nShall I try again, or would you like to rephrase your question?`,
        timestamp: new Date()
      }
      setMessages(prev => [...prev, errorMessage])
    } finally {
      setLoading(false)
    }
  }

  const handleCommandClick = (cmd: string) => {
    setInput(cmd + ' ')
    setShowCommands(false)
    textareaRef.current?.focus()
  }

  const clearHistory = () => {
    // Generate new session ID
    const newSession = generateSessionId()
    localStorage.setItem(SESSION_KEY, newSession)
    setSessionId(newSession)

    setMessages([{
      id: Date.now().toString(),
      role: 'assistant',
      content: getGexisClearMessage(),
      timestamp: new Date()
    }])
    localStorage.removeItem(STORAGE_KEY)
  }

  const exportConversation = async () => {
    try {
      const response = await apiClient.gexisExportConversation(sessionId, 'markdown')
      const data = response.data

      if (data.success && data.content) {
        // Create and download file
        const blob = new Blob([data.content], { type: 'text/markdown' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `gexis-conversation-${sessionId}.md`
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        URL.revokeObjectURL(url)
      }
    } catch (e) {
      console.error('Failed to export conversation:', e)
    }
  }

  const formatTime = (date: Date) => {
    return new Intl.DateTimeFormat('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      hour12: true
    }).format(date)
  }

  // Get message style based on type
  const getMessageStyle = (type?: string) => {
    switch (type) {
      case 'command':
        return 'border-l-4 border-cyan-500 bg-cyan-500/10'
      case 'briefing':
        return 'border-l-4 border-emerald-500 bg-emerald-500/10'
      case 'alert':
        return 'border-l-4 border-amber-500 bg-amber-500/10'
      default:
        return ''
    }
  }

  // Closed state - cool floating icon with glow effect
  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-6 right-6 z-50 w-16 h-16 rounded-full shadow-2xl flex items-center justify-center transition-all duration-300 hover:scale-110 group overflow-hidden"
        style={{
          background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #06b6d4 100%)',
          boxShadow: '0 0 30px rgba(99, 102, 241, 0.5), 0 0 60px rgba(139, 92, 246, 0.3)'
        }}
        title="Open GEXIS"
      >
        {/* Animated background rings */}
        <div className="absolute inset-0 rounded-full animate-ping opacity-20" style={{ background: 'linear-gradient(135deg, #6366f1, #06b6d4)' }} />
        <div className="absolute inset-2 rounded-full animate-pulse opacity-30" style={{ background: 'linear-gradient(135deg, #8b5cf6, #6366f1)' }} />

        {/* Icon */}
        <div className="relative z-10 flex items-center justify-center">
          <Bot className="w-7 h-7 text-white drop-shadow-lg" />
        </div>

        {/* Alert badge */}
        {alertCount > 0 && (
          <span className="absolute top-0 right-0 w-5 h-5 bg-amber-500 rounded-full border-2 border-white shadow-lg flex items-center justify-center">
            <span className="text-xs font-bold text-white">{alertCount}</span>
          </span>
        )}

        {/* Online indicator */}
        <span className="absolute bottom-1 right-1 w-3.5 h-3.5 bg-emerald-400 rounded-full border-2 border-white shadow-lg">
          <span className="absolute inset-0 bg-emerald-400 rounded-full animate-ping opacity-75" />
        </span>
      </button>
    )
  }

  // Minimized state - small bar with gradient
  if (isMinimized) {
    return (
      <div
        className="fixed bottom-6 right-6 z-50 rounded-full shadow-xl flex items-center gap-3 px-4 py-2.5 border border-white/10"
        style={{
          background: 'linear-gradient(135deg, rgba(99, 102, 241, 0.9) 0%, rgba(139, 92, 246, 0.9) 100%)',
          boxShadow: '0 0 20px rgba(99, 102, 241, 0.4)'
        }}
      >
        <Bot className="w-5 h-5 text-white" />
        <span className="text-sm text-white font-medium">{GEXIS_NAME}</span>
        {alertCount > 0 && (
          <span className="w-5 h-5 bg-amber-500 rounded-full flex items-center justify-center">
            <AlertTriangle className="w-3 h-3 text-white" />
          </span>
        )}
        <button
          onClick={() => setIsMinimized(false)}
          className="p-1 hover:bg-white/20 rounded-full transition-colors"
          title="Expand"
        >
          <Maximize2 className="w-4 h-4 text-white" />
        </button>
        <button
          onClick={() => setIsOpen(false)}
          className="p-1 hover:bg-white/20 rounded-full transition-colors"
          title="Close"
        >
          <X className="w-4 h-4 text-white" />
        </button>
      </div>
    )
  }

  // Full chat window
  return (
    <div
      className="fixed bottom-6 right-6 z-50 w-96 h-[520px] bg-background-card border border-border rounded-2xl shadow-2xl flex flex-col overflow-hidden"
      style={{ boxShadow: '0 0 40px rgba(99, 102, 241, 0.2), 0 25px 50px -12px rgba(0, 0, 0, 0.5)' }}
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
    >
      {/* Header with gradient */}
      <div
        className="flex items-center justify-between px-4 py-3 border-b border-white/10"
        style={{ background: 'linear-gradient(135deg, rgba(99, 102, 241, 0.95) 0%, rgba(139, 92, 246, 0.95) 100%)' }}
      >
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-white/20 flex items-center justify-center backdrop-blur-sm">
            <Bot className="w-5 h-5 text-white" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-white">{GEXIS_NAME}</h3>
            <p className="text-xs text-white/70">Session: {sessionId}</p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={toggleSound}
            className="p-2 hover:bg-white/20 rounded-full transition-colors"
            title={soundEnabled ? 'Mute sounds' : 'Enable sounds'}
          >
            {soundEnabled ? (
              <Volume2 className="w-4 h-4 text-white/80" />
            ) : (
              <VolumeX className="w-4 h-4 text-white/80" />
            )}
          </button>
          <button
            onClick={exportConversation}
            className="p-2 hover:bg-white/20 rounded-full transition-colors"
            title="Export conversation"
          >
            <Download className="w-4 h-4 text-white/80" />
          </button>
          <button
            onClick={clearHistory}
            className="p-2 hover:bg-white/20 rounded-full transition-colors"
            title="Clear chat"
          >
            <Trash2 className="w-4 h-4 text-white/80" />
          </button>
          <button
            onClick={() => setIsMinimized(true)}
            className="p-2 hover:bg-white/20 rounded-full transition-colors"
            title="Minimize"
          >
            <Minimize2 className="w-4 h-4 text-white/80" />
          </button>
          <button
            onClick={() => setIsOpen(false)}
            className="p-2 hover:bg-white/20 rounded-full transition-colors"
            title="Close"
          >
            <X className="w-4 h-4 text-white/80" />
          </button>
        </div>
      </div>

      {/* Drag overlay */}
      {isDragging && (
        <div className="absolute inset-0 bg-primary/20 backdrop-blur-sm border-2 border-dashed border-primary z-10 flex items-center justify-center rounded-2xl">
          <div className="text-center">
            <Image className="w-12 h-12 text-primary mx-auto mb-2" />
            <p className="text-primary font-medium">Drop image here</p>
          </div>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`flex gap-2.5 ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            {message.role === 'assistant' && (
              <div className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #6366f1, #8b5cf6)' }}>
                {message.type === 'command' ? (
                  <Terminal className="w-4 h-4 text-white" />
                ) : message.type === 'briefing' ? (
                  <Sparkles className="w-4 h-4 text-white" />
                ) : message.type === 'alert' ? (
                  <AlertTriangle className="w-4 h-4 text-white" />
                ) : (
                  <Bot className="w-4 h-4 text-white" />
                )}
              </div>
            )}

            <div className={`max-w-[80%] ${message.role === 'user' ? 'order-first' : ''}`}>
              {message.imageUrl && (
                <div className="mb-2 rounded-lg overflow-hidden border border-border">
                  <img
                    src={message.imageUrl}
                    alt="Uploaded"
                    className="max-w-full max-h-32 object-contain"
                  />
                </div>
              )}
              <div
                className={`rounded-2xl px-4 py-2.5 ${
                  message.role === 'user'
                    ? message.type === 'command'
                      ? 'bg-cyan-600 text-white rounded-br-md'
                      : 'bg-primary text-white rounded-br-md'
                    : `bg-background-hover text-text-primary rounded-bl-md ${getMessageStyle(message.type)}`
                }`}
              >
                <p className="text-sm whitespace-pre-wrap break-words leading-relaxed">{message.content}</p>
                <p className={`text-xs mt-1.5 ${message.role === 'user' ? 'text-white/60' : 'text-text-muted'}`}>
                  {formatTime(message.timestamp)}
                </p>
              </div>
            </div>

            {message.role === 'user' && (
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-background-hover flex items-center justify-center">
                <User className="w-4 h-4 text-text-secondary" />
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div className="flex gap-2.5">
            <div className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #6366f1, #8b5cf6)' }}>
              <Bot className="w-4 h-4 text-white animate-pulse" />
            </div>
            <div className="bg-background-hover rounded-2xl rounded-bl-md px-4 py-3">
              <div className="flex items-center gap-2">
                <div className="flex gap-1">
                  <div className="w-2 h-2 bg-primary rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                  <div className="w-2 h-2 bg-primary rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                  <div className="w-2 h-2 bg-primary rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
                <span className="text-sm text-text-muted">GEXIS is thinking...</span>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Command suggestions */}
      {showCommands && (
        <div className="px-3 py-2 border-t border-border bg-background-deep/50 max-h-32 overflow-y-auto">
          <p className="text-xs text-text-muted mb-2">Quick Commands:</p>
          <div className="flex flex-wrap gap-1">
            {QUICK_COMMANDS.filter(c => c.cmd.startsWith(input)).map((cmd) => (
              <button
                key={cmd.cmd}
                onClick={() => handleCommandClick(cmd.cmd)}
                className="px-2 py-1 text-xs bg-background-hover hover:bg-primary/20 rounded-lg transition-colors text-text-secondary hover:text-primary"
              >
                {cmd.cmd}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Image preview */}
      {selectedImage && (
        <div className="px-4 py-2 border-t border-border bg-background-hover/50">
          <div className="relative inline-block">
            <img
              src={selectedImage}
              alt="Selected"
              className="h-16 rounded-lg border border-border"
            />
            <button
              onClick={clearImage}
              className="absolute -top-2 -right-2 w-6 h-6 bg-danger rounded-full flex items-center justify-center shadow-lg hover:bg-danger/80 transition-colors"
            >
              <X className="w-3.5 h-3.5 text-white" />
            </button>
          </div>
        </div>
      )}

      {/* Input area */}
      <div className="p-3 border-t border-border bg-background-deep">
        <div className="flex gap-2 items-end">
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileInput}
            accept="image/*"
            className="hidden"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            className="p-2.5 hover:bg-background-hover rounded-xl transition-colors flex-shrink-0"
            title="Upload image"
            disabled={loading}
          >
            <Image className="w-5 h-5 text-text-secondary" />
          </button>
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                handleSend()
              }
            }}
            placeholder={`Ask GEXIS or type / for commands...`}
            className="flex-1 bg-background-card border border-border rounded-xl px-4 py-2.5 text-sm text-text-primary placeholder-text-muted resize-none min-h-[44px] max-h-[120px] focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50"
            disabled={loading}
            rows={1}
          />
          <button
            onClick={handleSend}
            disabled={(!input.trim() && !selectedImage) || loading}
            className="p-2.5 rounded-xl transition-all flex-shrink-0 disabled:opacity-50 disabled:cursor-not-allowed"
            style={{
              background: (!input.trim() && !selectedImage) || loading
                ? 'rgba(99, 102, 241, 0.5)'
                : 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)'
            }}
          >
            <Send className="w-5 h-5 text-white" />
          </button>
        </div>
        <p className="text-xs text-text-muted mt-1.5 text-center">
          Type / for commands | Shift+Enter for new line
        </p>
      </div>
    </div>
  )
}
