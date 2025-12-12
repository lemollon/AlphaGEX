'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
import { MessageSquare, Send, X, Minimize2, Maximize2, Image, Trash2, Bot, User, Loader2 } from 'lucide-react'
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
          content: "Hi! I'm your AI trading copilot. Ask me anything about market analysis, gamma exposure, or trading strategies. You can also upload images (charts, option chains, screenshots) for analysis!",
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

      if (response.data?.success && response.data?.data) {
        const aiMessage: Message = {
          id: (Date.now() + 1).toString(),
          role: 'assistant',
          content: response.data.data.analysis || response.data.data.response || 'Analysis completed.',
          timestamp: new Date()
        }
        setMessages(prev => [...prev, aiMessage])
      } else {
        throw new Error('Analysis service returned no data')
      }
    } catch (error: any) {
      console.error('Error getting AI response:', error)

      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: `**Error**: ${error?.message || 'Failed to get response'}. Please try again.`,
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
      content: "Chat history cleared. How can I help you today?",
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

  // Closed state - just the floating icon
  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-6 right-6 z-50 w-14 h-14 bg-primary hover:bg-primary/90 rounded-full shadow-lg flex items-center justify-center transition-all hover:scale-110 group"
        title="Open AI Copilot"
      >
        <MessageSquare className="w-6 h-6 text-white" />
        <span className="absolute -top-1 -right-1 w-3 h-3 bg-success rounded-full animate-pulse" />
      </button>
    )
  }

  // Minimized state - small bar
  if (isMinimized) {
    return (
      <div className="fixed bottom-6 right-6 z-50 bg-background-card border border-border rounded-lg shadow-xl flex items-center gap-2 px-4 py-2">
        <Bot className="w-5 h-5 text-primary" />
        <span className="text-sm text-text-primary font-medium">AI Copilot</span>
        <button
          onClick={() => setIsMinimized(false)}
          className="p-1 hover:bg-background-hover rounded"
          title="Expand"
        >
          <Maximize2 className="w-4 h-4 text-text-secondary" />
        </button>
        <button
          onClick={() => setIsOpen(false)}
          className="p-1 hover:bg-background-hover rounded"
          title="Close"
        >
          <X className="w-4 h-4 text-text-secondary" />
        </button>
      </div>
    )
  }

  // Full chat window
  return (
    <div
      className="fixed bottom-6 right-6 z-50 w-96 h-[500px] bg-background-card border border-border rounded-xl shadow-2xl flex flex-col overflow-hidden"
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-background-deep border-b border-border">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center">
            <Bot className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-text-primary">AI Copilot</h3>
            <p className="text-xs text-text-muted">Ask anything about trading</p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={clearHistory}
            className="p-1.5 hover:bg-background-hover rounded transition-colors"
            title="Clear chat history"
          >
            <Trash2 className="w-4 h-4 text-text-secondary" />
          </button>
          <button
            onClick={() => setIsMinimized(true)}
            className="p-1.5 hover:bg-background-hover rounded transition-colors"
            title="Minimize"
          >
            <Minimize2 className="w-4 h-4 text-text-secondary" />
          </button>
          <button
            onClick={() => setIsOpen(false)}
            className="p-1.5 hover:bg-background-hover rounded transition-colors"
            title="Close"
          >
            <X className="w-4 h-4 text-text-secondary" />
          </button>
        </div>
      </div>

      {/* Drag overlay */}
      {isDragging && (
        <div className="absolute inset-0 bg-primary/10 border-2 border-dashed border-primary z-10 flex items-center justify-center">
          <div className="text-center">
            <Image className="w-12 h-12 text-primary mx-auto mb-2" />
            <p className="text-primary font-medium">Drop image here</p>
          </div>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`flex gap-2 ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            {message.role === 'assistant' && (
              <div className="flex-shrink-0 w-7 h-7 rounded-full bg-primary/20 flex items-center justify-center">
                <Bot className="w-4 h-4 text-primary" />
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
                className={`rounded-lg px-3 py-2 ${
                  message.role === 'user'
                    ? 'bg-primary text-white'
                    : 'bg-background-hover text-text-primary'
                }`}
              >
                <p className="text-sm whitespace-pre-wrap break-words">{message.content}</p>
                <p className={`text-xs mt-1 ${message.role === 'user' ? 'text-white/60' : 'text-text-muted'}`}>
                  {formatTime(message.timestamp)}
                </p>
              </div>
            </div>

            {message.role === 'user' && (
              <div className="flex-shrink-0 w-7 h-7 rounded-full bg-background-hover flex items-center justify-center">
                <User className="w-4 h-4 text-text-secondary" />
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div className="flex gap-2">
            <div className="flex-shrink-0 w-7 h-7 rounded-full bg-primary/20 flex items-center justify-center">
              <Bot className="w-4 h-4 text-primary" />
            </div>
            <div className="bg-background-hover rounded-lg px-3 py-2">
              <div className="flex gap-1.5">
                <Loader2 className="w-4 h-4 text-primary animate-spin" />
                <span className="text-sm text-text-muted">Analyzing...</span>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Image preview */}
      {selectedImage && (
        <div className="px-3 py-2 border-t border-border bg-background-hover">
          <div className="relative inline-block">
            <img
              src={selectedImage}
              alt="Selected"
              className="h-16 rounded border border-border"
            />
            <button
              onClick={clearImage}
              className="absolute -top-2 -right-2 w-5 h-5 bg-danger rounded-full flex items-center justify-center"
            >
              <X className="w-3 h-3 text-white" />
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
            className="p-2 hover:bg-background-hover rounded-lg transition-colors flex-shrink-0"
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
            className="flex-1 bg-background-card border border-border rounded-lg px-3 py-2 text-sm text-text-primary placeholder-text-muted resize-none min-h-[40px] max-h-[120px] focus:outline-none focus:ring-2 focus:ring-primary/50"
            disabled={loading}
            rows={1}
          />
          <button
            onClick={handleSend}
            disabled={(!input.trim() && !selectedImage) || loading}
            className="p-2 bg-primary hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors flex-shrink-0"
          >
            <Send className="w-5 h-5 text-white" />
          </button>
        </div>
        <p className="text-xs text-text-muted mt-1.5 text-center">
          Press Enter to send, Shift+Enter for new line
        </p>
      </div>
    </div>
  )
}
