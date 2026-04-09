import { useState, useEffect, useRef } from "react"
import { useParams, useNavigate, useLocation } from "react-router-dom"
import { api, streamMessage, type Session, type Message } from "@/lib/api/client"
import { cn } from "@/lib/utils"

type LeftTab = "problem" | "chat" | "notes"

// Countdown timer hook
function useTimer(initialSeconds = 45 * 60) {
  const [seconds, setSeconds] = useState(initialSeconds)
  useEffect(() => {
    const id = setInterval(() => setSeconds((s) => Math.max(0, s - 1)), 1000)
    return () => clearInterval(id)
  }, [])
  const m = String(Math.floor(seconds / 60)).padStart(2, "0")
  const s = String(seconds % 60).padStart(2, "0")
  return `${m}:${s}`
}

export default function SessionPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const sessionId = Number(id)
  const timer = useTimer()

  const [session, setSession] = useState<Session | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState("")
  const [streaming, setStreaming] = useState(false)
  const [finishing, setFinishing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<LeftTab>("chat")
  const [notes, setNotes] = useState("")

  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    api.getSession(sessionId).then((s) => {
      setSession(s)
      const openingFromNav = (location.state as { openingMessage?: string })?.openingMessage
      if (s.messages.length > 0) {
        setMessages(s.messages)
      } else if (openingFromNav) {
        setMessages([{ role: "assistant", content: openingFromNav }])
      }
    })
  }, [sessionId, location.state])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  const lastAiMessage = [...messages].reverse().find((m) => m.role === "assistant")

  async function handleSend() {
    if (!input.trim() || streaming) return
    const userMsg: Message = { role: "user", content: input.trim() }
    setMessages((prev) => [...prev, userMsg])
    setInput("")
    setStreaming(true)
    setError(null)
    setActiveTab("chat")
    setMessages((prev) => [...prev, { role: "assistant", content: "" }])

    try {
      let full = ""
      for await (const chunk of streamMessage(sessionId, userMsg.content)) {
        full += chunk
        setMessages((prev) => {
          const updated = [...prev]
          updated[updated.length - 1] = { role: "assistant", content: full }
          return updated
        })
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Stream error")
      setMessages((prev) => prev.slice(0, -1))
    } finally {
      setStreaming(false)
      inputRef.current?.focus()
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  async function handleFinish() {
    setFinishing(true)
    try {
      await api.finishSession(sessionId)
      navigate(`/session/${sessionId}/scorecard`)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to generate scorecard")
      setFinishing(false)
    }
  }

  return (
    <div className="h-screen overflow-hidden flex flex-col bg-background">
      {/* ── Top Nav ── */}
      <header className="flex justify-between items-center w-full px-6 py-3 border-b border-border bg-background shrink-0 z-50">
        <div className="flex items-center gap-2">
          <img src="/logo.jpg" alt="grillme" className="h-9 w-9 rounded-full" />
          <span className="text-xl font-black tracking-tighter uppercase font-wordmark"><span className="text-on-surface">grill</span><span className="text-primary">me</span></span>
        </div>

        <div className="flex items-center gap-4 ml-auto">
          {/* Timer */}
          <div className="flex items-center gap-2 bg-surface-container-low px-3 py-1.5 rounded-xl border border-outline-variant/20">
            <span
              className="material-symbols-outlined text-tertiary text-lg"
              style={{ fontVariationSettings: "'FILL' 1" }}
            >
              timer
            </span>
            <span className="font-mono text-sm font-bold tracking-tight text-on-surface">
              {timer}
            </span>
          </div>

          <button
            className="px-4 py-1.5 text-xs font-bold rounded-xl bg-surface-container-highest text-on-surface hover:bg-surface-bright transition-colors active:scale-[0.97]"
            onClick={handleFinish}
            disabled={finishing || messages.length < 2}
          >
            {finishing ? (
              <span className="material-symbols-outlined text-sm animate-spin">
                progress_activity
              </span>
            ) : (
              "Finish & Score"
            )}
          </button>
          <button className="px-4 py-1.5 text-xs font-bold rounded-xl shimmer-gradient text-on-primary hover:opacity-90 transition-opacity active:scale-[0.97]">
            Submit Solution
          </button>

          <div className="flex items-center gap-3 ml-2 pl-4 border-l border-outline-variant/20">
            <span className="material-symbols-outlined text-outline cursor-pointer hover:text-on-surface transition-colors">
              settings
            </span>
            <span className="material-symbols-outlined text-outline cursor-pointer hover:text-on-surface transition-colors">
              help
            </span>
          </div>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* ── Left Sidebar ── */}
        <aside className="flex flex-col items-center py-6 h-full w-20 gap-8 bg-background border-r border-border shrink-0">
          <div className="flex flex-col items-center gap-6 w-full">
            {(
              [
                { icon: "description", label: "Problem", tab: "problem" as LeftTab },
                { icon: "chat", label: "Chat", tab: "chat" as LeftTab },
                { icon: "sticky_note_2", label: "Notes", tab: "notes" as LeftTab },
                { icon: "draw", label: "Whiteboard", tab: null },
                { icon: "videocam", label: "Video", tab: null },
              ] as const
            ).map(({ icon, label, tab }) => {
              const active = tab && activeTab === tab
              return (
                <button
                  key={label}
                  onClick={() => tab && setActiveTab(tab)}
                  className={cn(
                    "flex flex-col items-center gap-1 w-full py-2 transition-all active:scale-90 duration-100 relative",
                    active
                      ? "text-primary before:absolute before:left-0 before:h-8 before:w-1 before:bg-primary before:rounded-r-full"
                      : "text-outline hover:text-on-surface",
                  )}
                >
                  <span
                    className="material-symbols-outlined text-2xl"
                    style={active ? { fontVariationSettings: "'FILL' 1" } : undefined}
                  >
                    {icon}
                  </span>
                  <span className="text-[10px] font-semibold uppercase tracking-widest font-label">
                    {label}
                  </span>
                </button>
              )
            })}
          </div>

          <div className="mt-auto flex flex-col items-center gap-4">
            <button
              onClick={() => navigate("/")}
              className="text-[10px] font-bold text-error uppercase tracking-tighter bg-error-container/20 px-2 py-1 rounded-xl hover:bg-error-container/40 transition-colors"
            >
              End
            </button>
          </div>
        </aside>

        {/* ── Main workspace ── */}
        <div className="flex flex-1 overflow-hidden">
          {/* ── LEFT PANEL 40% ── */}
          <div className="w-[40%] flex flex-col border-r border-border bg-surface-container-low">
            {/* Interviewer avatar */}
            <div className="relative m-4 mb-0 rounded-xl overflow-hidden bg-surface-container-lowest shrink-0 h-48">
              <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-surface-container to-surface-container-highest">
                <span
                  className="material-symbols-outlined text-7xl text-outline/30"
                  style={{ fontVariationSettings: "'FILL' 1" }}
                >
                  face
                </span>
              </div>
              {session && (
                <div className="absolute bottom-3 left-3 flex items-center gap-2 bg-black/40 backdrop-blur-md px-3 py-1.5 rounded-xl border border-white/10">
                  <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                  <div>
                    <p className="text-xs font-bold leading-none text-white">Interviewer</p>
                    <p className="text-[10px] text-on-surface-variant font-medium">
                      {session.company ?? "AI"} · {session.level ?? "Senior"}
                    </p>
                  </div>
                </div>
              )}
            </div>

            {/* Live transcription */}
            <div className="mx-4 mt-3 px-4 py-3 bg-surface-container rounded-xl border border-outline-variant/20 shrink-0">
              <div className="flex items-start gap-2">
                <span className="material-symbols-outlined text-primary text-sm mt-0.5">
                  interpreter_mode
                </span>
                <div className="flex-1 min-w-0">
                  {lastAiMessage ? (
                    <p className="text-sm text-on-surface leading-relaxed line-clamp-3">
                      "{lastAiMessage.content}"
                    </p>
                  ) : (
                    <p className="text-sm text-outline italic">Waiting to begin…</p>
                  )}
                  {streaming && (
                    <div className="flex items-center gap-1 mt-1.5">
                      <div className="w-1.5 h-1.5 bg-outline rounded-full animate-bounce" />
                      <div className="w-1.5 h-1.5 bg-outline rounded-full animate-bounce [animation-delay:0.2s]" />
                      <div className="w-1.5 h-1.5 bg-outline rounded-full animate-bounce [animation-delay:0.4s]" />
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Tabs */}
            <div className="flex-1 flex flex-col mx-4 mt-3 mb-4 bg-surface-container rounded-xl overflow-hidden border border-outline-variant/20">
              <div className="flex border-b border-outline-variant/30 shrink-0">
                {(["problem", "chat", "notes"] as LeftTab[]).map((t) => (
                  <button
                    key={t}
                    onClick={() => setActiveTab(t)}
                    className={cn(
                      "flex-1 py-2.5 text-[10px] font-bold uppercase tracking-widest transition-colors",
                      activeTab === t
                        ? "text-primary border-b-2 border-primary bg-surface-container-high"
                        : "text-outline hover:text-on-surface",
                    )}
                  >
                    {t}
                  </button>
                ))}
              </div>

              <div className="flex-1 overflow-y-auto no-scrollbar p-4">
                {/* Problem tab */}
                {activeTab === "problem" && session && (
                  <div className="space-y-4">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h2 className="text-lg font-headline font-extrabold tracking-tight text-on-surface">
                        {session.role ?? "Role"}
                      </h2>
                      {session.level && (
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-tertiary-container/20 text-tertiary border border-tertiary/30">
                          {session.level}
                        </span>
                      )}
                    </div>
                    {session.company && (
                      <p className="text-sm text-on-surface-variant">
                        <span className="text-primary font-semibold">{session.company}</span>
                      </p>
                    )}
                    {session.persona && (
                      <div className="bg-surface-container-lowest p-4 rounded-xl border border-outline-variant/20">
                        <p className="text-[10px] font-bold text-outline uppercase tracking-wider mb-2">
                          Interviewer Persona
                        </p>
                        <p className="text-xs text-on-surface-variant leading-relaxed">
                          {session.persona}
                        </p>
                      </div>
                    )}
                  </div>
                )}

                {/* Notes tab */}
                {activeTab === "notes" && (
                  <textarea
                    className="w-full h-full min-h-[160px] bg-transparent text-sm text-on-surface placeholder:text-outline resize-none focus:outline-none font-mono"
                    placeholder="Scratch pad — jot down ideas…"
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                  />
                )}

                {/* Chat tab (preview of last few messages) */}
                {activeTab === "chat" && (
                  <div className="space-y-3 text-sm">
                    {messages.slice(-4).map((msg, i) => (
                      <div key={i} className={cn("flex", msg.role === "user" ? "justify-end" : "justify-start")}>
                        <div
                          className={cn(
                            "max-w-[85%] px-3 py-2 rounded-xl text-xs leading-relaxed",
                            msg.role === "user"
                              ? "bg-primary/15 text-primary rounded-br-sm"
                              : "bg-surface-container-highest text-on-surface rounded-bl-sm",
                          )}
                        >
                          {msg.content || <span className="text-outline italic">thinking…</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* ── RIGHT PANEL 60% ── */}
          <div className="flex-1 flex flex-col bg-surface-container-lowest">
            {/* Panel header */}
            <div className="flex items-center justify-between px-4 py-2 bg-surface-container-low border-b border-border shrink-0">
              <div className="flex items-center gap-2">
                <div className="flex items-center gap-2 px-3 py-1 bg-surface-container-highest rounded-lg text-xs font-semibold text-on-surface border border-outline-variant/20">
                  <span className="material-symbols-outlined text-sm text-primary">
                    chat_bubble
                  </span>
                  Interview Chat
                </div>
                {session?.company && (
                  <span className="text-xs text-outline font-mono">
                    {session.company} / {session.role}
                  </span>
                )}
              </div>
              <div className="flex gap-2">
                <button className="p-1.5 text-outline hover:text-on-surface transition-colors">
                  <span className="material-symbols-outlined text-lg">format_align_left</span>
                </button>
              </div>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto no-scrollbar px-6 py-4 space-y-4 font-body text-sm">
              {messages.length === 0 && (
                <div className="h-full flex items-center justify-center text-outline text-sm">
                  Loading session…
                </div>
              )}
              {messages.map((msg, i) => (
                <div
                  key={i}
                  className={cn("flex", msg.role === "user" ? "justify-end" : "justify-start")}
                >
                  {msg.role === "assistant" && (
                    <div className="w-7 h-7 rounded-full bg-gradient-to-br from-primary/30 to-primary-container/30 border border-primary/20 flex items-center justify-center mr-2 shrink-0 mt-0.5">
                      <span className="material-symbols-outlined text-sm text-primary" style={{ fontVariationSettings: "'FILL' 1" }}>
                        smart_toy
                      </span>
                    </div>
                  )}
                  <div
                    className={cn(
                      "max-w-[72%] rounded-2xl px-4 py-3 leading-relaxed whitespace-pre-wrap text-sm",
                      msg.role === "user"
                        ? "bg-primary/10 text-primary border border-primary/15 rounded-br-sm"
                        : "bg-surface-container text-on-surface border border-outline-variant/15 rounded-bl-sm",
                    )}
                  >
                    {msg.content}
                    {streaming && i === messages.length - 1 && msg.role === "assistant" && (
                      <span className="inline-block w-1.5 h-4 ml-0.5 bg-primary/60 animate-pulse align-middle rounded-sm" />
                    )}
                  </div>
                </div>
              ))}
              {error && (
                <div className="flex items-center gap-2 text-error text-xs px-3 py-2 bg-error-container/10 rounded-xl border border-error/20">
                  <span className="material-symbols-outlined text-sm">error</span>
                  {error}
                </div>
              )}
              <div ref={bottomRef} />
            </div>

            {/* Input — styled like the terminal footer */}
            <div className="border-t border-border bg-surface-container-low shrink-0">
              <div className="flex items-center justify-between px-4 py-2 border-b border-border/50">
                <div className="flex gap-4">
                  <span className="text-[10px] font-bold uppercase tracking-widest text-primary border-b border-primary">
                    Response
                  </span>
                </div>
                <span className="text-[10px] text-outline">Enter ↵ to send · Shift+Enter for newline</span>
              </div>
              <div className="flex items-end gap-2 p-4">
                <div className="flex items-center gap-2 text-secondary mr-1 self-end mb-1">
                  <span className="font-mono text-sm">$</span>
                </div>
                <textarea
                  ref={inputRef}
                  className="flex-1 bg-transparent font-mono text-sm text-on-surface placeholder:text-outline resize-none focus:outline-none min-h-[40px] max-h-[140px]"
                  placeholder="Your answer…"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  disabled={streaming}
                  rows={2}
                />
                <button
                  onClick={handleSend}
                  disabled={streaming || !input.trim()}
                  className="p-2 rounded-xl shimmer-gradient text-on-primary hover:opacity-90 transition-opacity disabled:opacity-30 disabled:pointer-events-none active:scale-[0.97] shrink-0 self-end"
                >
                  {streaming ? (
                    <span className="material-symbols-outlined text-sm animate-spin">
                      progress_activity
                    </span>
                  ) : (
                    <span className="material-symbols-outlined text-sm">send</span>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
