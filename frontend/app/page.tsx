"use client"

import { useState, useRef, useEffect } from "react"
import ReactMarkdown from "react-markdown"
import { Send, Plus, Copy, Check, Menu, X, Loader2, Terminal, Zap, Database, Activity } from "lucide-react"

const API_BASE = "http://localhost:8000"

type Message = {
  role: "user" | "assistant"
  content: string
}

type ToolStatus = {
  name: string
  status: "calling" | "completed"
}

type Session = {
  id: string
  timestamp: string
  messages: Message[]
}

const SUGGESTED_PROMPTS = [
  { icon: Database, text: "What log groups are available?" },
  { icon: Activity, text: "Show me recent errors in CoverLetterGen" },
  { icon: Zap, text: "Ingest logs for /aws/lambda/CoverLetterGen" },
  { icon: Terminal, text: "Fetch the latest live logs for CoverLetterGen" },
]

export default function ChatPage() {
  const [sessions, setSessions] = useState<Session[]>([])
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState("")
  const [isStreaming, setIsStreaming] = useState(false)
  const [toolStatus, setToolStatus] = useState<ToolStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const createNewSession = async () => {
    try {
      const res = await fetch(`${API_BASE}/session/new`)
      const data = await res.json()
      const newSession: Session = {
        id: data.thread_id || data.id || crypto.randomUUID(),
        timestamp: new Date().toLocaleString(),
        messages: [],
      }
      setSessions((prev) => [newSession, ...prev])
      setCurrentSessionId(newSession.id)
      setMessages([])
      setError(null)
      return newSession.id; 

    } catch {
      const newSession: Session = {
        id: crypto.randomUUID(),
        timestamp: new Date().toLocaleString(),
        messages: [],
      }
      setSessions((prev) => [newSession, ...prev])
      setCurrentSessionId(newSession.id)
      setMessages([])
    
       return newSession.id; 
    }
  }

  const switchSession = (sessionId: string) => {
    if (sessionId === currentSessionId) return
    
    if (currentSessionId) {
      setSessions((prev) =>
        prev.map((s) => (s.id === currentSessionId ? { ...s, messages } : s))
      )
    }
    
    const session = sessions.find((s) => s.id === sessionId)
    if (session) {
      setCurrentSessionId(sessionId)
      setMessages([...session.messages])
      setError(null)
      setToolStatus(null)
    }
  }

  const sendMessage = async (text: string) => {
    if (!text.trim() || isStreaming) return
     let sessionId = currentSessionId; // ← capture current value
     if (!sessionId) {
       sessionId = await createNewSession(); // ← use returned value
     }

    const userMessage: Message = { role: "user", content: text }
    setMessages((prev) => [...prev, userMessage])
    setInput("")
    setIsStreaming(true)
    setError(null)
    setToolStatus(null)

    let assistantContent = ""

    try {
      const response = await fetch(`${API_BASE}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, thread_id: sessionId }),
      })

      if (!response.ok) throw new Error("Failed to connect")

      const reader = response.body?.getReader()
      const decoder = new TextDecoder()

      setMessages((prev) => [...prev, { role: "assistant", content: "" }])

      while (reader) {
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value)
        const lines = chunk.split("\n")

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue
          const data = line.slice(6)
          if (!data) continue

          try {
            const event = JSON.parse(data)

            if (event.type === "tool_call") {
              setToolStatus({ name: event.name, status: "calling" })
            } else if (event.type === "tool_result") {
              setToolStatus((prev) =>
                prev ? { ...prev, status: "completed" } : null
              )
              setTimeout(() => setToolStatus(null), 2000)
            } else if (event.type === "token") {
              assistantContent += event.content
              setMessages((prev) => {
                const updated = [...prev]
                updated[updated.length - 1] = {
                  role: "assistant",
                  content: assistantContent,
                }
                return updated
              })
            } else if (event.type === "done") {
              setIsStreaming(false)
            } else if (event.type === "error") {
              setError(event.message || "An error occurred")
              setIsStreaming(false)
            }
          } catch {
            // Skip malformed JSON
          }
        }
      }
    } catch {
      setError("Failed to connect to the server")
    } finally {
      setIsStreaming(false)
      if (currentSessionId) {
        setSessions((prev) =>
          prev.map((s) =>
            s.id === currentSessionId
              ? { ...s, messages: [...messages, userMessage, { role: "assistant", content: assistantContent }] }
              : s
          )
        )
      }
    }
  }

  useEffect(() => {
    if (currentSessionId && messages.length > 0 && !isStreaming) {
      setSessions((prev) =>
        prev.map((s) =>
          s.id === currentSessionId ? { ...s, messages } : s
        )
      )
    }
  }, [messages, currentSessionId, isStreaming])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      sendMessage(input)
    }
  }

  const copyToClipboard = async (text: string, index: number) => {
    await navigator.clipboard.writeText(text)
    setCopiedIndex(index)
    setTimeout(() => setCopiedIndex(null), 2000)
  }

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: "#0f0d1a" }}>
      {/* Sidebar */}
      <aside
        className={`${sidebarOpen ? "w-72" : "w-0"} flex-shrink-0 transition-all duration-300 overflow-hidden`}
        style={{ background: "#0a0812", borderRight: sidebarOpen ? "1px solid #2a2540" : "none" }}
      >
        <div className="p-4" style={{ borderBottom: "1px solid #2a2540" }}>
          <button
            onClick={createNewSession}
            className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-sm font-medium transition-all hover:opacity-90"
            style={{ 
              background: "linear-gradient(135deg, rgba(99, 102, 241, 0.15), rgba(168, 85, 247, 0.15))",
              border: "1px solid rgba(99, 102, 241, 0.4)"
            }}
          >
            <Plus size={18} style={{ color: "#818cf8" }} />
            <span style={{ 
              background: "linear-gradient(90deg, #818cf8, #a855f7)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
              fontWeight: 600
            }}>
              New Session
            </span>
          </button>
        </div>
        <div className="overflow-y-auto p-3" style={{ height: "calc(100% - 80px)" }}>
          <div className="text-xs uppercase tracking-widest px-3 py-2 font-medium" style={{ color: "#6b7280" }}>
            Sessions
          </div>
          {sessions.length === 0 && (
            <div className="px-3 py-6 text-sm text-center" style={{ color: "#6b7280" }}>
              No sessions yet
            </div>
          )}
          {sessions.map((session) => (
            <button
              key={session.id}
              onClick={() => switchSession(session.id)}
              className="w-full text-left px-4 py-3 text-sm rounded-xl mb-2 transition-all"
              style={{
                background: currentSessionId === session.id 
                  ? "linear-gradient(135deg, rgba(99, 102, 241, 0.15), rgba(168, 85, 247, 0.15))"
                  : "transparent",
                border: currentSessionId === session.id 
                  ? "1px solid rgba(99, 102, 241, 0.4)"
                  : "1px solid transparent"
              }}
            >
              <div className="flex items-center gap-3">
                <div 
                  className="w-8 h-8 rounded-lg flex items-center justify-center"
                  style={{ 
                    background: currentSessionId === session.id 
                      ? "rgba(99, 102, 241, 0.2)" 
                      : "rgba(45, 40, 70, 0.5)" 
                  }}
                >
                  <Terminal 
                    size={14} 
                    style={{ color: currentSessionId === session.id ? "#818cf8" : "#6b7280" }} 
                  />
                </div>
                <span 
                  className="font-mono text-xs"
                  style={{ color: currentSessionId === session.id ? "#e5e7eb" : "#6b7280" }}
                >
                  {session.timestamp}
                </span>
              </div>
            </button>
          ))}
        </div>
      </aside>

      {/* Main Chat Area */}
      <main className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <header 
          className="flex items-center gap-4 px-6 py-4"
          style={{ background: "rgba(20, 17, 35, 0.8)", borderBottom: "1px solid #2a2540" }}
        >
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="p-2.5 rounded-xl transition-colors"
            style={{ color: "#e5e7eb" }}
          >
            {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
          <div className="flex items-center gap-4">
            <div className="relative">
              <div 
                className="w-12 h-12 rounded-xl flex items-center justify-center"
                style={{ 
                  background: "linear-gradient(135deg, rgba(99, 102, 241, 0.3), rgba(168, 85, 247, 0.3))",
                  border: "1px solid rgba(99, 102, 241, 0.4)",
                  boxShadow: "0 0 20px rgba(99, 102, 241, 0.3)"
                }}
              >
                <Terminal size={24} style={{ color: "#818cf8" }} />
              </div>
              <div 
                className="absolute -bottom-0.5 -right-0.5 w-3.5 h-3.5 rounded-full animate-pulse"
                style={{ 
                  background: "linear-gradient(135deg, #34d399, #10b981)",
                  border: "2px solid #0f0d1a"
                }}
              />
            </div>
            <div>
              <h1 
                className="text-xl font-bold"
                style={{ 
                  background: "linear-gradient(90deg, #818cf8, #a855f7)",
                  WebkitBackgroundClip: "text",
                  WebkitTextFillColor: "transparent"
                }}
              >
                CloudWatch Log Analyst
              </h1>
              <p className="text-xs" style={{ color: "#6b7280" }}>AI-powered log analysis</p>
            </div>
          </div>
        </header>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-6">
          {messages.length === 0 && !currentSessionId && (
            <div className="flex flex-col items-center justify-center h-full gap-10 max-w-2xl mx-auto">
              <div className="text-center space-y-4">
                <div 
                  className="w-24 h-24 rounded-2xl flex items-center justify-center mx-auto"
                  style={{ 
                    background: "linear-gradient(135deg, rgba(99, 102, 241, 0.3), rgba(168, 85, 247, 0.3))",
                    border: "1px solid rgba(99, 102, 241, 0.4)",
                    boxShadow: "0 0 30px rgba(99, 102, 241, 0.3)"
                  }}
                >
                  <Terminal size={48} style={{ color: "#818cf8" }} />
                </div>
                <h2 
                  className="text-3xl font-bold"
                  style={{ 
                    background: "linear-gradient(90deg, #e5e7eb, #818cf8, #a855f7)",
                    WebkitBackgroundClip: "text",
                    WebkitTextFillColor: "transparent"
                  }}
                >
                  Welcome to CloudWatch Log Analyst
                </h2>
                <p className="max-w-md text-base" style={{ color: "#6b7280" }}>
                  Your AI assistant for analyzing AWS CloudWatch logs. Ask me anything about your log groups, errors, or patterns.
                </p>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 w-full">
                {SUGGESTED_PROMPTS.map((prompt) => (
                  <button
                    key={prompt.text}
                    onClick={() => {
                      createNewSession().then(() => sendMessage(prompt.text))
                    }}
                    className="group flex items-start gap-4 text-left px-5 py-5 rounded-2xl text-sm transition-all"
                    style={{ 
                      background: "rgba(20, 17, 35, 0.6)",
                      border: "1px solid #2a2540"
                    }}
                  >
                    <div 
                      className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 transition-all"
                      style={{ 
                        background: "linear-gradient(135deg, rgba(99, 102, 241, 0.2), rgba(168, 85, 247, 0.2))",
                        border: "1px solid rgba(99, 102, 241, 0.2)"
                      }}
                    >
                      <prompt.icon size={18} style={{ color: "#818cf8" }} />
                    </div>
                    <span style={{ color: "#9ca3af", lineHeight: 1.5 }}>
                      {prompt.text}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="max-w-4xl mx-auto space-y-5">
            {messages.map((msg, i) => (
              <div
                key={i}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className="max-w-[85%] rounded-2xl px-5 py-4"
                  style={{
                    background: msg.role === "user"
                      ? "linear-gradient(135deg, rgba(99, 102, 241, 0.2), rgba(168, 85, 247, 0.2))"
                      : "rgba(20, 17, 35, 0.8)",
                    border: msg.role === "user"
                      ? "1px solid rgba(99, 102, 241, 0.3)"
                      : "1px solid #2a2540"
                  }}
                >
                  {msg.role === "assistant" ? (
                    <div className="prose prose-invert prose-sm max-w-none" style={{ color: "#e5e7eb" }}>
                      <ReactMarkdown
                        components={{
                          code({ className, children, ...props }) {
                            const isBlock = className?.includes("language-")
                            const codeContent = String(children).replace(/\n$/, "")
                            if (isBlock) {
                              return (
                                <div className="relative my-4 group">
                                  <div 
                                    className="absolute top-0 left-0 right-0 h-9 rounded-t-xl flex items-center px-4 gap-2"
                                    style={{ background: "rgba(45, 40, 70, 0.8)" }}
                                  >
                                    <div className="w-3 h-3 rounded-full" style={{ background: "rgba(239, 68, 68, 0.7)" }} />
                                    <div className="w-3 h-3 rounded-full" style={{ background: "rgba(234, 179, 8, 0.7)" }} />
                                    <div className="w-3 h-3 rounded-full" style={{ background: "rgba(34, 197, 94, 0.7)" }} />
                                    <span className="ml-3 text-xs font-mono" style={{ color: "#6b7280" }}>
                                      {className?.replace("language-", "") || "code"}
                                    </span>
                                  </div>
                                  <button
                                    onClick={() => copyToClipboard(codeContent, i)}
                                    className="absolute top-2 right-3 p-1.5 rounded-lg text-xs opacity-0 group-hover:opacity-100 transition-opacity"
                                    style={{ background: "rgba(45, 40, 70, 0.5)" }}
                                  >
                                    {copiedIndex === i ? (
                                      <Check size={14} style={{ color: "#34d399" }} />
                                    ) : (
                                      <Copy size={14} style={{ color: "#9ca3af" }} />
                                    )}
                                  </button>
                                  <pre 
                                    className="pt-12 pb-4 px-4 rounded-xl overflow-x-auto font-mono text-sm"
                                    style={{ background: "rgba(10, 8, 18, 0.9)", border: "1px solid #2a2540" }}
                                  >
                                    <code style={{ color: "rgba(129, 140, 248, 0.9)" }} {...props}>{children}</code>
                                  </pre>
                                </div>
                              )
                            }
                            return (
                              <code
                                className="px-1.5 py-0.5 rounded-md font-mono text-sm"
                                style={{ background: "rgba(99, 102, 241, 0.1)", color: "#818cf8" }}
                                {...props}
                              >
                                {children}
                              </code>
                            )
                          },
                          pre({ children }) {
                            return <>{children}</>
                          },
                        }}
                      >
                        {msg.content}
                      </ReactMarkdown>
                      {isStreaming && i === messages.length - 1 && (
                        <span 
                          className="inline-block w-2.5 h-5 ml-1 rounded-sm animate-pulse"
                          style={{ background: "linear-gradient(180deg, #818cf8, #a855f7)" }}
                        />
                      )}
                    </div>
                  ) : (
                    <p className="whitespace-pre-wrap" style={{ color: "#e5e7eb" }}>{msg.content}</p>
                  )}
                </div>
              </div>
            ))}

            {/* Tool Status */}
            {toolStatus && (
              <div className="flex justify-start">
                <div
                  className="inline-flex items-center gap-3 px-5 py-3 rounded-xl text-sm font-medium"
                  style={{
                    background: toolStatus.status === "calling"
                      ? "rgba(234, 179, 8, 0.1)"
                      : "rgba(34, 197, 94, 0.1)",
                    border: toolStatus.status === "calling"
                      ? "1px solid rgba(234, 179, 8, 0.3)"
                      : "1px solid rgba(34, 197, 94, 0.3)",
                    color: toolStatus.status === "calling" ? "#facc15" : "#34d399",
                    boxShadow: toolStatus.status === "completed" 
                      ? "0 0 20px rgba(34, 197, 94, 0.2)" 
                      : "none"
                  }}
                >
                  {toolStatus.status === "calling" ? (
                    <>
                      <Loader2 size={16} className="animate-spin" />
                      <span>Executing: {toolStatus.name}</span>
                    </>
                  ) : (
                    <>
                      <Check size={16} />
                      <span>Completed: {toolStatus.name}</span>
                    </>
                  )}
                </div>
              </div>
            )}

            {/* Error */}
            {error && (
              <div 
                className="px-5 py-4 rounded-xl flex items-center gap-3"
                style={{ 
                  background: "rgba(239, 68, 68, 0.1)",
                  border: "1px solid rgba(239, 68, 68, 0.3)",
                  color: "#f87171"
                }}
              >
                <div className="w-2.5 h-2.5 rounded-full animate-pulse" style={{ background: "#ef4444" }} />
                {error}
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Input Area */}
        <div 
          className="p-6"
          style={{ 
            background: "linear-gradient(to top, rgba(20, 17, 35, 0.8), transparent)",
            borderTop: "1px solid #2a2540"
          }}
        >
          <div className="flex gap-3 max-w-4xl mx-auto">
            <div className="flex-1 relative">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask about your CloudWatch logs..."
                disabled={isStreaming}
                rows={1}
                className="w-full rounded-2xl px-5 py-4 pr-14 resize-none focus:outline-none disabled:opacity-50 transition-all"
                style={{ 
                  background: "#141123",
                  border: "1px solid #2a2540",
                  color: "#e5e7eb",
                  minHeight: "56px",
                  maxHeight: "200px"
                }}
              />
              <button
                onClick={() => sendMessage(input)}
                disabled={isStreaming || !input.trim()}
                className="absolute right-3 top-1/2 -translate-y-1/2 w-10 h-10 flex items-center justify-center rounded-xl transition-all disabled:opacity-30"
                style={{ 
                  background: "linear-gradient(135deg, #6366f1, #a855f7)",
                  boxShadow: "0 0 15px rgba(99, 102, 241, 0.3)"
                }}
              >
                {isStreaming ? (
                  <Loader2 size={18} className="animate-spin" style={{ color: "white" }} />
                ) : (
                  <Send size={18} style={{ color: "white" }} />
                )}
              </button>
            </div>
          </div>
          <p className="text-xs text-center mt-4" style={{ color: "#6b7280" }}>
            Press Enter to send, Shift+Enter for new line
          </p>
        </div>
      </main>
    </div>
  )
}
