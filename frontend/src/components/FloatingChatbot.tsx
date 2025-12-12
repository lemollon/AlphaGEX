'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
import { Send, X, Minimize2, Maximize2, Image, Trash2, User, Loader2, Bot } from 'lucide-react'
import { apiClient } from '@/lib/api'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  imageUrl?: string // Base64 image data URL
}

const STORAGE_KEY = 'alphagex_chat_history'
const MAX_STORED_MESSAGES = 50

// Cool animated AI robot icon component
function AIRobotIcon({ className = "w-6 h-6", animate = false }: { className?: string, animate?: boolean }) {
  return (
    <div className="relative">
      <Bot className={`${className} text-white relative z-10 ${animate ? 'animate-pulse' : ''}`} />
    </div>
  )
}

export default function FloatingChatbot() {
  const [isOpen, setIsOpen] = useState(false)
  const [isMinimized, setIsMinimized] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [selectedImage, setSelectedImage] = useState<string | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

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
        // Add welcome message if no history
        setMessages([{
          id: '1',
          role: 'assistant',
          content: "Hey! I'm your AI trading copilot powered by Claude. Ask me anything about market analysis, gamma exposure, or trading strategies. You can also drop images (charts, option chains) for analysis!",
          timestamp: new Date()
        }])
      }
    } catch (e) {
      console.error('Failed to load chat history:', e)
    }
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

  const handleSend = async () => {
    if ((!input.trim() && !selectedImage) || loading) return

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input || (selectedImage ? '[Image uploaded for analysis]' : ''),
      timestamp: new Date(),
      imageUrl: selectedImage || undefined
    }

    setMessages(prev => [...prev, userMessage])
    const currentInput = input
    const currentImage = selectedImage
    setInput('')
    setSelectedImage(null)
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
    setLoading(true)

    try {
      let response

      if (currentImage) {
        // Use image analysis endpoint
        response = await apiClient.analyzeWithImage({
          symbol: 'SPY',
          query: currentInput || 'Please analyze this image and provide trading insights.',
          image_data: currentImage
        })
      } else {
        // Use regular analysis endpoint
        response = await apiClient.analyzeMarket({
          symbol: 'SPY',
          query: currentInput,
          market_data: {},
          gamma_intel: {}
        })
      }

      // Handle various response formats
      const responseData = response.data
      let analysisText = ''

      if (responseData?.success && responseData?.data) {
        // New format: { success: true, data: { analysis: "..." } }
        analysisText = responseData.data.analysis || responseData.data.response || ''
      } else if (responseData?.response) {
        // Old format: { response: "..." }
        analysisText = responseData.response
      } else if (responseData?.analysis) {
        // Direct analysis: { analysis: "..." }
        analysisText = responseData.analysis
      } else if (typeof responseData === 'string') {
        analysisText = responseData
      }

      if (analysisText) {
        const aiMessage: Message = {
          id: (Date.now() + 1).toString(),
          role: 'assistant',
          content: analysisText,
          timestamp: new Date()
        }
        setMessages(prev => [...prev, aiMessage])
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
        content: `Sorry, I encountered an error: ${errorMsg}\n\nPlease try again or rephrase your question.`,
        timestamp: new Date()
      }
      setMessages(prev => [...prev, errorMessage])
    } finally {
      setLoading(false)
    }
  }

  const clearHistory = () => {
    setMessages([{
      id: Date.now().toString(),
      role: 'assistant',
      content: "Chat cleared! What would you like to analyze?",
      timestamp: new Date()
    }])
    localStorage.removeItem(STORAGE_KEY)
  }

  const formatTime = (date: Date) => {
    return new Intl.DateTimeFormat('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      hour12: true
    }).format(date)
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
        title="Open AI Copilot"
      >
        {/* Animated background rings */}
        <div className="absolute inset-0 rounded-full animate-ping opacity-20" style={{ background: 'linear-gradient(135deg, #6366f1, #06b6d4)' }} />
        <div className="absolute inset-2 rounded-full animate-pulse opacity-30" style={{ background: 'linear-gradient(135deg, #8b5cf6, #6366f1)' }} />

        {/* Icon */}
        <div className="relative z-10 flex items-center justify-center">
          <Bot className="w-7 h-7 text-white drop-shadow-lg" />
        </div>

        {/* Online indicator */}
        <span className="absolute top-1 right-1 w-3.5 h-3.5 bg-emerald-400 rounded-full border-2 border-white shadow-lg">
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
        <span className="text-sm text-white font-medium">AI Copilot</span>
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
            <h3 className="text-sm font-bold text-white">AI Copilot</h3>
            <p className="text-xs text-white/70">Powered by Claude</p>
          </div>
        </div>
        <div className="flex items-center gap-1">
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
                <Bot className="w-4 h-4 text-white" />
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
                    ? 'bg-primary text-white rounded-br-md'
                    : 'bg-background-hover text-text-primary rounded-bl-md'
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
                <Loader2 className="w-4 h-4 text-primary animate-spin" />
                <span className="text-sm text-text-muted">Thinking...</span>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

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
            placeholder="Ask about markets, upload charts..."
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
      </div>
    </div>
  )
}
