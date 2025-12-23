'use client'

import { useState, useEffect } from 'react'
import Navigation from '../../../components/Navigation'
import { apiClient } from '../../../lib/api'
import { MessageSquare, Clock, Search, User, Bot } from 'lucide-react'

interface Conversation {
  id: number
  timestamp: string
  user_message: string
  ai_response: string
  context: string
  session_id: string
}

export default function ConversationHistory() {
  const [loading, setLoading] = useState(true)
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [filteredConversations, setFilteredConversations] = useState<Conversation[]>([])
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedConversation, setSelectedConversation] = useState<Conversation | null>(null)

  useEffect(() => {
    fetchConversations()
  }, [])

  useEffect(() => {
    if (searchQuery) {
      const filtered = conversations.filter(
        (conv) =>
          conv.user_message.toLowerCase().includes(searchQuery.toLowerCase()) ||
          conv.ai_response.toLowerCase().includes(searchQuery.toLowerCase())
      )
      setFilteredConversations(filtered)
    } else {
      setFilteredConversations(conversations)
    }
  }, [searchQuery, conversations])

  const fetchConversations = async () => {
    try {
      setLoading(true)
      const res = await apiClient.getConversations(100)

      if (res.data.success) {
        setConversations(res.data.conversations)
        setFilteredConversations(res.data.conversations)
      }
    } catch (error) {
      console.error('Error fetching conversations:', error)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex h-screen bg-gray-900">
      <Navigation />

      <div className="flex-1 overflow-auto p-8">
        <div className="max-w-7xl mx-auto">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-white mb-2">Conversation History</h1>
            <p className="text-gray-400">AI Copilot chat logs and analysis sessions</p>
          </div>

          {/* Search */}
          <div className="mb-6">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
              <input
                type="text"
                placeholder="Search conversations..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-10 pr-4 py-2 bg-gray-800 border border-gray-700 text-white rounded-lg focus:outline-none focus:border-blue-500"
              />
            </div>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-20">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
            </div>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Conversation List */}
              <div className="bg-gray-800 rounded-xl shadow-lg">
                <div className="p-6 border-b border-gray-700">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <MessageSquare className="h-5 w-5 text-blue-500" />
                      <h2 className="text-xl font-semibold text-white">Recent Conversations</h2>
                    </div>
                    <span className="text-sm text-gray-400">{filteredConversations.length} total</span>
                  </div>
                </div>

                <div className="overflow-auto max-h-[calc(100vh-300px)]">
                  {filteredConversations.length === 0 ? (
                    <div className="p-8 text-center text-gray-400">
                      <MessageSquare className="h-12 w-12 mx-auto mb-3 text-gray-600" />
                      <p>No conversations found</p>
                      <p className="text-sm mt-1">Start chatting with the AI Copilot</p>
                    </div>
                  ) : (
                    <div className="divide-y divide-gray-700">
                      {filteredConversations.map((conv) => (
                        <div
                          key={conv.id}
                          onClick={() => setSelectedConversation(conv)}
                          className={`p-4 cursor-pointer hover:bg-gray-750 transition ${
                            selectedConversation?.id === conv.id ? 'bg-gray-750' : ''
                          }`}
                        >
                          <div className="flex items-start gap-3">
                            <User className="h-5 w-5 text-blue-500 mt-1 flex-shrink-0" />
                            <div className="flex-1 min-w-0">
                              <p className="text-sm text-white mb-1 line-clamp-2">{conv.user_message}</p>
                              <div className="flex items-center gap-2 text-xs text-gray-400">
                                <Clock className="h-3 w-3" />
                                <span>{new Date(conv.timestamp).toLocaleString()}</span>
                              </div>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Conversation Detail */}
              <div className="bg-gray-800 rounded-xl shadow-lg">
                <div className="p-6 border-b border-gray-700">
                  <h2 className="text-xl font-semibold text-white">Conversation Detail</h2>
                </div>

                <div className="p-6">
                  {selectedConversation ? (
                    <div className="space-y-6">
                      {/* User Message */}
                      <div className="bg-blue-500/10 border border-blue-500/20 rounded-lg p-4">
                        <div className="flex items-center gap-2 mb-2">
                          <User className="h-4 w-4 text-blue-500" />
                          <span className="text-sm font-medium text-blue-400">You</span>
                          <span className="text-xs text-gray-500">
                            {new Date(selectedConversation.timestamp).toLocaleString()}
                          </span>
                        </div>
                        <p className="text-white whitespace-pre-wrap">{selectedConversation.user_message}</p>
                      </div>

                      {/* AI Response */}
                      <div className="bg-green-500/10 border border-green-500/20 rounded-lg p-4">
                        <div className="flex items-center gap-2 mb-2">
                          <Bot className="h-4 w-4 text-green-500" />
                          <span className="text-sm font-medium text-green-400">AI Copilot</span>
                        </div>
                        <p className="text-white whitespace-pre-wrap">{selectedConversation.ai_response}</p>
                      </div>

                      {/* Context */}
                      {selectedConversation.context && (
                        <div className="bg-gray-750 rounded-lg p-4 border border-gray-700">
                          <h3 className="text-sm font-medium text-gray-400 mb-2">Context</h3>
                          <p className="text-sm text-gray-300">{selectedConversation.context}</p>
                        </div>
                      )}

                      {/* Session Info */}
                      <div className="bg-gray-750 rounded-lg p-4 border border-gray-700">
                        <h3 className="text-sm font-medium text-gray-400 mb-2">Session Info</h3>
                        <div className="grid grid-cols-2 gap-2 text-sm">
                          <div className="text-gray-400">Conversation ID:</div>
                          <div className="text-white font-mono">{selectedConversation.id}</div>
                          <div className="text-gray-400">Session ID:</div>
                          <div className="text-white font-mono text-xs truncate">
                            {selectedConversation.session_id}
                          </div>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="text-center text-gray-400 py-20">
                      <MessageSquare className="h-16 w-16 mx-auto mb-4 text-gray-600" />
                      <p>Select a conversation to view details</p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
