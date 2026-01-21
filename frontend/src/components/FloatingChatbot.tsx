'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
import { Send, X, Minimize2, Maximize2, Image, Trash2, User, Loader2, Bot, Download, Volume2, VolumeX, Sparkles, Terminal, AlertTriangle, Wrench, CheckCircle, XCircle } from 'lucide-react'
import { apiClient } from '@/lib/api'
import ReactMarkdown from 'react-markdown'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  imageUrl?: string // Base64 image data URL
  type?: 'normal' | 'command' | 'briefing' | 'alert' // Message type for styling
  toolsUsed?: Array<{ tool: string; input: any }> // Tools used by GEXIS
  pendingConfirmation?: { // For bot control confirmations
    action: string
    bot: string
    confirmationId: string
  }
}

// GEXIS Configuration
const GEXIS_NAME = 'GEXIS'
const GEXIS_FULL_NAME = 'Gamma Exposure eXpert Intelligence System'
const USER_NAME = 'Optionist Prime'

const STORAGE_KEY = 'alphagex_chat_history'
const SESSION_KEY = 'alphagex_session_id'
const SOUND_PREF_KEY = 'alphagex_sound_enabled'
const MAX_STORED_MESSAGES = 50
const STREAMING_ENABLED = true // Enable streaming responses
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://alphagex-api.onrender.com'

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

// Get Central Time date/time (all AlphaGEX operations use Chicago time)
function getCentralTime(): Date {
  return new Date(new Date().toLocaleString('en-US', { timeZone: 'America/Chicago' }))
}

// Get time-based greeting for GEXIS (Central Time)
function getTimeGreeting(): string {
  const hour = getCentralTime().getHours()
  if (hour >= 5 && hour < 12) return 'Good morning'
  if (hour >= 12 && hour < 17) return 'Good afternoon'
  return 'Good evening'
}

// Get GEXIS welcome message - JARVIS-style sophisticated greeting
function getGexisWelcomeMessage(): string {
  const greeting = getTimeGreeting()
  const ct = getCentralTime()
  const dayOfWeek = ct.toLocaleDateString('en-US', { weekday: 'long', timeZone: 'America/Chicago' })
  const isWeekend = ct.getDay() === 0 || ct.getDay() === 6
  const hour = ct.getHours()

  // Dynamic status based on time
  let marketContext = ''
  if (isWeekend) {
    marketContext = `Markets are closed for the weekend. Perfect time for strategy review and preparation.`
  } else if (hour < 8) {
    marketContext = `Pre-market analysis available. European markets are active.`
  } else if (hour >= 8 && hour < 9) {
    marketContext = `Pre-market session active. Monitoring overnight developments.`
  } else if (hour >= 9 && hour < 15) {
    marketContext = `Markets are LIVE. All systems monitoring in real-time.`
  } else if (hour >= 15 && hour < 16) {
    marketContext = `Power hour in progress. Elevated gamma activity expected.`
  } else {
    marketContext = `After-hours session. Preparing tomorrow's intelligence.`
  }

  return `${greeting}, ${USER_NAME}. GEXIS online.

**━━━ SYSTEM STATUS ━━━**
◉ Neural Core: Active
◉ Market Feed: Connected
◉ Trading Bots: Standing By
◉ Risk Monitor: Vigilant

**━━━ ${dayOfWeek.toUpperCase()} BRIEFING ━━━**
${marketContext}

I have full situational awareness of your AlphaGEX ecosystem—real-time gamma exposure, dealer positioning, bot performance, and your complete trading history.

*"Shall I run a market scan, or do you have a specific objective today, Prime?"*`
}

// Get GEXIS chat cleared message - JARVIS-style
function getGexisClearMessage(): string {
  return `Memory banks cleared, ${USER_NAME}.

All previous context purged. Systems recalibrated.

*Standing by for new directives.*`
}

// Cached AudioContext to prevent memory leak from creating new contexts
let cachedAudioContext: AudioContext | null = null

function getAudioContext(): AudioContext | null {
  if (typeof window === 'undefined') return null
  try {
    if (!cachedAudioContext) {
      cachedAudioContext = new (window.AudioContext || (window as any).webkitAudioContext)()
    }
    return cachedAudioContext
  } catch {
    return null
  }
}

// Play notification sound
function playNotificationSound() {
  try {
    const audioContext = getAudioContext()
    if (!audioContext) return

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
  } catch {
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
  const [pendingConfirmation, setPendingConfirmation] = useState<{
    action: string
    bot: string
    confirmationId: string
    message: string
  } | null>(null)
  const [streamingMessage, setStreamingMessage] = useState<string>('')
  const [streamingTools, setStreamingTools] = useState<string[]>([])
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Initialize session ID (with SSR/private browsing safety)
  useEffect(() => {
    try {
      let storedSession = localStorage?.getItem(SESSION_KEY)
      if (!storedSession) {
        storedSession = generateSessionId()
        try {
          localStorage?.setItem(SESSION_KEY, storedSession)
        } catch {
          // localStorage write failed (quota exceeded or private browsing)
        }
      }
      setSessionId(storedSession)
    } catch {
      // localStorage not available - use generated session
      setSessionId(generateSessionId())
    }
  }, [])

  // Load sound preference (with SSR/private browsing safety)
  useEffect(() => {
    try {
      const pref = localStorage?.getItem(SOUND_PREF_KEY)
      if (pref !== null) {
        setSoundEnabled(pref === 'true')
      }
    } catch {
      // localStorage not available - use default
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

  // Maximum image size: 5MB
  const MAX_IMAGE_SIZE = 5 * 1024 * 1024

  const handleImageSelect = useCallback((file: File) => {
    if (!file.type.startsWith('image/')) {
      return
    }

    // Validate file size to prevent API timeouts and memory issues
    if (file.size > MAX_IMAGE_SIZE) {
      const sizeMB = (file.size / (1024 * 1024)).toFixed(1)
      setMessages(prev => [...prev, {
        id: Date.now().toString(),
        role: 'assistant',
        content: `Image too large (${sizeMB}MB). Maximum size is 5MB. Please select a smaller image.`,
        timestamp: new Date()
      }])
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
      let toolsUsed: Array<{ tool: string; input: any }> = []
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
        } else if (STREAMING_ENABLED) {
          // Use streaming agentic chat for better UX
          try {
            const streamResult = await handleStreamingChat(currentInput)
            analysisText = streamResult.text
            toolsUsed = streamResult.toolsUsed
            if (streamResult.pendingConfirmation) {
              setPendingConfirmation(streamResult.pendingConfirmation)
            }
          } catch (streamError) {
            console.warn('Streaming failed, falling back to regular endpoint:', streamError)
            // Fallback to non-streaming
            response = await apiClient.gexisAgenticChat({
              query: currentInput,
              session_id: sessionId,
              market_data: {}
            })
            const data = response.data
            if (data.success && data.data) {
              analysisText = data.data.analysis || ''
              if (data.data.tools_used?.length > 0) {
                toolsUsed = data.data.tools_used
              }
              if (data.data.pending_confirmation) {
                setPendingConfirmation(data.data.pending_confirmation)
              }
            }
          }
        } else {
          // Use regular agentic chat endpoint
          response = await apiClient.gexisAgenticChat({
            query: currentInput,
            session_id: sessionId,
            market_data: {}
          })
          const data = response.data

          if (data.success && data.data) {
            analysisText = data.data.analysis || ''
            // Capture tools used for display
            if (data.data.tools_used && data.data.tools_used.length > 0) {
              toolsUsed = data.data.tools_used
            }
            // Check for pending bot confirmation
            if (data.data.pending_confirmation) {
              setPendingConfirmation(data.data.pending_confirmation)
            }
          } else if (data.error) {
            throw new Error(data.error)
          }
        }

        // Handle API client response format (for non-streaming)
        if (response && 'data' in response) {
          const responseData = response.data
          if (responseData?.success && responseData?.data) {
            analysisText = responseData.data.analysis || responseData.data.response || ''
            // Also capture tools from this path
            if (responseData.data.tools_used && responseData.data.tools_used.length > 0) {
              toolsUsed = responseData.data.tools_used
            }
            // Also check for pending confirmation from this path
            if (responseData.data.pending_confirmation) {
              setPendingConfirmation(responseData.data.pending_confirmation)
            }
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
          type: messageType,
          toolsUsed: toolsUsed.length > 0 ? toolsUsed : undefined
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

  // Handle bot action confirmation
  const handleConfirmation = async (confirm: boolean) => {
    if (!pendingConfirmation) return

    setLoading(true)
    try {
      const response = await apiClient.gexisConfirmAction({
        session_id: sessionId,
        confirm
      })

      const resultMessage: Message = {
        id: Date.now().toString(),
        role: 'assistant',
        content: confirm
          ? `**${pendingConfirmation.bot.toUpperCase()} ${pendingConfirmation.action.toUpperCase()}** command executed successfully.`
          : `**${pendingConfirmation.bot.toUpperCase()} ${pendingConfirmation.action.toUpperCase()}** action cancelled.`,
        timestamp: new Date(),
        type: confirm ? 'command' : 'normal'
      }
      setMessages(prev => [...prev, resultMessage])

      if (soundEnabled) {
        playNotificationSound()
      }
    } catch (error: any) {
      const errorMessage: Message = {
        id: Date.now().toString(),
        role: 'assistant',
        content: `Failed to ${confirm ? 'confirm' : 'cancel'} the action. ${error?.message || 'Please try again.'}`,
        timestamp: new Date()
      }
      setMessages(prev => [...prev, errorMessage])
    } finally {
      setPendingConfirmation(null)
      setLoading(false)
    }
  }

  // Handle streaming chat response
  const handleStreamingChat = async (query: string): Promise<{ text: string; toolsUsed: any[]; pendingConfirmation: any }> => {
    return new Promise(async (resolve, reject) => {
      let fullText = ''
      let toolsUsed: any[] = []
      let pendingConf = null

      try {
        const response = await fetch(`${API_URL}/api/ai/gexis/agentic-chat/stream`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            query,
            session_id: sessionId
          })
        })

        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`)
        }

        // Explicit null check for streaming support
        if (!response.body) {
          throw new Error('Streaming not supported - response body is null')
        }

        const reader = response.body.getReader()
        if (!reader) {
          throw new Error('Failed to get stream reader - browser may not support ReadableStream')
        }

        const decoder = new TextDecoder()

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          const chunk = decoder.decode(value, { stream: true })
          const lines = chunk.split('\n')

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6))

                if (data.type === 'text') {
                  fullText += data.content
                  setStreamingMessage(fullText)
                } else if (data.type === 'tool') {
                  if (data.status === 'executing') {
                    setStreamingTools(prev => [...prev, data.name])
                  }
                } else if (data.type === 'done') {
                  toolsUsed = data.tools_used || []
                } else if (data.type === 'error') {
                  throw new Error(data.message)
                }
              } catch (parseError) {
                // Ignore parse errors for incomplete chunks
              }
            }
          }
        }

        resolve({ text: fullText, toolsUsed, pendingConfirmation: pendingConf })
      } catch (error) {
        reject(error)
      } finally {
        setStreamingMessage('')
        setStreamingTools([])
      }
    })
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
      className="fixed bottom-0 right-0 sm:bottom-6 sm:right-6 z-50 w-full sm:w-96 h-[100dvh] sm:h-[520px] max-w-full bg-background-card border border-border sm:rounded-2xl shadow-2xl flex flex-col overflow-hidden"
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
                {message.role === 'assistant' ? (
                  <div className="text-sm prose prose-sm prose-invert max-w-none break-words leading-relaxed [&>p]:m-0 [&>p]:mb-2 [&>p:last-child]:mb-0 [&>ul]:my-1 [&>ol]:my-1 [&>li]:my-0.5 [&>h1]:text-base [&>h2]:text-sm [&>h3]:text-sm [&>h1]:font-bold [&>h2]:font-semibold [&>h3]:font-medium [&>strong]:text-primary [&>h1]:mb-2 [&>h2]:mb-1.5 [&>h3]:mb-1">
                    <ReactMarkdown>{message.content}</ReactMarkdown>
                  </div>
                ) : (
                  <p className="text-sm whitespace-pre-wrap break-words leading-relaxed">{message.content}</p>
                )}
                {/* Tools used indicator */}
                {message.toolsUsed && message.toolsUsed.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2 pt-2 border-t border-border/30">
                    <Wrench className="w-3 h-3 text-text-muted mr-1" />
                    {message.toolsUsed.map((tool, idx) => (
                      <span
                        key={idx}
                        className="text-xs px-1.5 py-0.5 rounded bg-primary/20 text-primary-light"
                        title={JSON.stringify(tool.input, null, 2)}
                      >
                        {tool.tool.replace('get_', '').replace(/_/g, ' ')}
                      </span>
                    ))}
                  </div>
                )}
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
            <div className="bg-background-hover rounded-2xl rounded-bl-md px-4 py-3 max-w-[85%]">
              {/* Show streaming message if available */}
              {streamingMessage ? (
                <div>
                  <div className="text-sm prose prose-sm prose-invert max-w-none break-words leading-relaxed">
                    <ReactMarkdown>{streamingMessage}</ReactMarkdown>
                    <span className="animate-pulse">▊</span>
                  </div>
                  {streamingTools.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2 pt-2 border-t border-border/30">
                      <Wrench className="w-3 h-3 text-text-muted mr-1 animate-spin" />
                      {streamingTools.map((tool, idx) => (
                        <span key={idx} className="text-xs px-1.5 py-0.5 rounded bg-primary/20 text-primary-light">
                          {tool.replace('get_', '').replace(/_/g, ' ')}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  {streamingTools.length > 0 ? (
                    <>
                      <Loader2 className="w-4 h-4 text-primary animate-spin" />
                      <span className="text-sm text-text-muted">
                        Fetching {streamingTools[streamingTools.length - 1]?.replace('get_', '').replace(/_/g, ' ')}...
                      </span>
                    </>
                  ) : (
                    <>
                      <div className="flex gap-1">
                        <div className="w-2 h-2 bg-primary rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                        <div className="w-2 h-2 bg-primary rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                        <div className="w-2 h-2 bg-primary rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                      </div>
                      <span className="text-sm text-text-muted">GEXIS is thinking...</span>
                    </>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Bot Action Confirmation UI */}
        {pendingConfirmation && !loading && (
          <div className="flex gap-2.5">
            <div className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center bg-amber-500/20">
              <AlertTriangle className="w-4 h-4 text-amber-400" />
            </div>
            <div className="bg-amber-500/10 border border-amber-500/30 rounded-2xl rounded-bl-md px-4 py-3 max-w-[85%]">
              <p className="text-sm font-medium text-amber-300 mb-2">
                {pendingConfirmation.message}
              </p>
              <p className="text-xs text-text-muted mb-3">
                This will affect live trading operations for <span className="text-amber-400 font-semibold">{pendingConfirmation.bot.toUpperCase()}</span>
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => handleConfirmation(true)}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-green-600 hover:bg-green-500 text-white rounded-lg transition-colors"
                >
                  <CheckCircle className="w-4 h-4" />
                  Confirm
                </button>
                <button
                  onClick={() => handleConfirmation(false)}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-red-600 hover:bg-red-500 text-white rounded-lg transition-colors"
                >
                  <XCircle className="w-4 h-4" />
                  Cancel
                </button>
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
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="sentences"
            spellCheck="true"
            inputMode="text"
            enterKeyHint="send"
            data-gramm="false"
            data-gramm_editor="false"
            data-enable-grammarly="false"
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
