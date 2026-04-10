import { useEffect, useRef, useState } from "react"
import { useLocation, useNavigate, useParams } from "react-router-dom"
import Editor from "@monaco-editor/react"
import {
  api,
  streamMessage,
  type Message,
  type RunResult,
  type Session,
  type TestResult,
} from "@/lib/api/client"
import { cn } from "@/lib/utils"
import { Sidebar } from "@/components/Sidebar"

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
  const [code, setCode] = useState("")
  const [runResult, setRunResult] = useState<RunResult | null>(null)
  const [testResult, setTestResult] = useState<TestResult | null>(null)
  const [terminalTab, setTerminalTab] = useState<"console" | "tests">("console")
  const [running, setRunning] = useState(false)
  const [showClosingPrompt, setShowClosingPrompt] = useState(false)

  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    api.getSession(sessionId).then((s) => {
      setSession(s)
      const navState = location.state as { openingMessage?: string; starterCode?: string } | null
      const openingFromNav = navState?.openingMessage
      const starterFromNav = navState?.starterCode
      if (s.messages.length > 0) {
        setMessages(s.messages.filter((m) => m.role !== "system"))
      } else if (openingFromNav) {
        setMessages([{ role: "assistant", content: openingFromNav }])
      }
      if (s.starter_code) {
        setCode(s.starter_code)
      } else if (starterFromNav) {
        setCode(starterFromNav)
      }
    })
  }, [sessionId, location.state])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  async function handleRunCode() {
    if (!code.trim()) return
    setRunning(true)
    setTerminalTab("console")
    try {
      const result = await api.runCode(code)
      setRunResult(result)
      api.shareCode(sessionId, code, result, undefined).catch(() => {})
    } catch (e) {
      setRunResult({
        stdout: "",
        stderr: e instanceof Error ? e.message : "Error",
        exit_code: -1,
        runtime_ms: 0,
        timed_out: false,
      })
    } finally {
      setRunning(false)
    }
  }

  async function handleRunTests() {
    if (!code.trim() || !session?.test_cases) return
    setRunning(true)
    setTerminalTab("tests")
    try {
      const result = await api.runTests(code, sessionId)
      setTestResult(result)
      api.shareCode(sessionId, code, undefined, result).catch(() => {})
    } catch (e) {
      console.error(e)
    } finally {
      setRunning(false)
    }
  }

  function handleEditorKeyDown(e: React.KeyboardEvent) {
    if (!(e.metaKey || e.ctrlKey) || e.key !== "Enter") return
    e.preventDefault()
    if (e.shiftKey) {
      void handleRunTests()
    } else {
      void handleRunCode()
    }
  }

  async function handleSend() {
    if (!input.trim() || streaming) return
    const userMsg: Message = { role: "user", content: input.trim() }
    setMessages((prev) => [...prev, userMsg, { role: "assistant", content: "" }])
    setInput("")
    setStreaming(true)
    setError(null)

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

  function handleFinishClick() {
    setShowClosingPrompt(true)
  }

  async function handleFinishConfirmed() {
    setShowClosingPrompt(false)
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
      <header className="flex justify-between items-center w-full px-6 py-3 border-b border-border bg-background shrink-0 z-50">
        <div className="flex items-center gap-2">
          <img src="/logo.jpg" alt="grillme" className="h-9 w-9 rounded-full" />
          <span className="text-xl font-black tracking-tighter uppercase font-wordmark">
            <span className="text-on-surface">grill</span>
            <span className="text-primary">me</span>
          </span>
        </div>
        <div className="flex items-center gap-4 ml-auto">
          <div className="flex items-center gap-2 bg-surface-container-low px-3 py-1.5 rounded-xl border border-outline-variant/20">
            <span className="material-symbols-outlined text-tertiary text-lg" style={{ fontVariationSettings: "'FILL' 1" }}>
              timer
            </span>
            <span className="font-mono text-sm font-bold tracking-tight text-on-surface">{timer}</span>
          </div>
          <button
            className="px-4 py-1.5 text-xs font-bold rounded-xl bg-surface-container-highest text-on-surface hover:bg-surface-bright transition-colors active:scale-[0.97] disabled:opacity-40"
            onClick={handleFinishClick}
            disabled={finishing || messages.length < 2}
          >
            {finishing ? (
              <span className="material-symbols-outlined text-sm animate-spin">progress_activity</span>
            ) : (
              "Finish & Score"
            )}
          </button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <Sidebar activePage="home" />

        <div className="flex flex-1 overflow-hidden">
          <div className="w-1/2 border-r border-border bg-surface-container-low flex flex-col">
            <div className="flex items-center justify-between px-4 py-2 bg-surface-container-low border-b border-border shrink-0">
              <div className="flex items-center gap-2 px-3 py-1 bg-surface-container-highest rounded-lg text-xs font-semibold text-on-surface border border-outline-variant/20">
                <span className="w-2 h-2 rounded-full bg-blue-400" />
                Python 3.13
              </div>
              <div className="flex gap-2">
                <button
                  onClick={handleRunCode}
                  disabled={running || !code.trim()}
                  className="px-3 py-1 text-xs font-semibold rounded-lg bg-surface-container-highest text-on-surface-variant hover:bg-surface-bright transition-colors disabled:opacity-40"
                >
                  Run Code
                </button>
                <button
                  onClick={handleRunTests}
                  disabled={running || !code.trim() || !session?.test_cases}
                  className="px-3 py-1 text-xs font-semibold rounded-lg bg-primary/20 text-primary hover:bg-primary/30 transition-colors disabled:opacity-40"
                >
                  Run Tests
                </button>
              </div>
            </div>

            <div className="h-[70%] border-b border-border">
              <div onKeyDown={handleEditorKeyDown} className="h-full">
                <Editor
                  height="100%"
                  defaultLanguage="python"
                  theme="vs-dark"
                  value={code}
                  onChange={(v) => setCode(v ?? "")}
                  options={{
                    fontSize: 13,
                    minimap: { enabled: false },
                    lineNumbers: "on",
                    scrollBeyondLastLine: false,
                    automaticLayout: true,
                  }}
                />
              </div>
            </div>

            <div className="h-[30%] flex flex-col">
              <div className="flex items-center gap-3 px-4 py-1.5 border-b border-border bg-surface-container-low">
                <button
                  className={cn(
                    "text-[10px] font-bold uppercase tracking-widest",
                    terminalTab === "console"
                      ? "text-primary border-b border-primary"
                      : "text-outline hover:text-on-surface",
                  )}
                  onClick={() => setTerminalTab("console")}
                >
                  Console
                </button>
                <button
                  className={cn(
                    "text-[10px] font-bold uppercase tracking-widest",
                    terminalTab === "tests"
                      ? "text-primary border-b border-primary"
                      : "text-outline hover:text-on-surface",
                  )}
                  onClick={() => setTerminalTab("tests")}
                >
                  Test Results
                </button>
              </div>
              <div className="flex-1 overflow-y-auto no-scrollbar p-4 font-mono text-xs">
                {terminalTab === "console" ? (
                  runResult ? (
                    <div className="space-y-2">
                      {runResult.timed_out && (
                        <div className="rounded-md border border-yellow-500/40 bg-yellow-500/10 px-2 py-1 text-yellow-300">
                          Execution timed out (10s limit)
                        </div>
                      )}
                      {runResult.stdout && <pre className="whitespace-pre-wrap text-on-surface">{runResult.stdout}</pre>}
                      {runResult.stderr && <pre className="whitespace-pre-wrap text-error">{runResult.stderr}</pre>}
                      {!runResult.stdout && !runResult.stderr && (
                        <p className="text-outline">No output.</p>
                      )}
                      <p className="text-on-surface-variant">Exit: {runResult.exit_code} · {runResult.runtime_ms}ms</p>
                    </div>
                  ) : (
                    <p className="text-outline">Run your code to see output</p>
                  )
                ) : testResult ? (
                  <div className="space-y-2">
                    <p className="text-on-surface-variant font-semibold">
                      {testResult.passed}/{testResult.total} passed · {testResult.runtime_ms}ms
                    </p>
                    {testResult.results.map((r) => (
                      <div key={r.id} className={cn("rounded-md px-2 py-1", r.passed ? "bg-green-500/10" : "bg-red-500/10")}>
                        <p className={cn("font-semibold", r.passed ? "text-green-400" : "text-red-400")}>
                          {r.passed ? "✓" : "✗"} Test {r.id}
                        </p>
                        {r.error ? (
                          <p className="text-red-400">input={r.input} → error: {r.error}</p>
                        ) : (
                          <p className="text-on-surface-variant">
                            input={r.input} → expected {r.expected}, got {r.actual}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-outline">Run tests to see results</p>
                )}
              </div>
            </div>
          </div>

          <div className="w-1/2 flex flex-col bg-surface-container-lowest">
            <div className="p-4 border-b border-border bg-surface-container-low">
              <div className="flex items-center gap-2 mb-2">
                <h2 className="text-base font-bold text-on-surface">
                  {session?.company ?? "Coding Problem"}
                </h2>
                {session?.difficulty && (
                  <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-primary/10 text-primary border border-primary/30">
                    {session.difficulty}
                  </span>
                )}
              </div>
              <p className="text-sm text-on-surface-variant whitespace-pre-wrap">
                {session?.problem_statement || (location.state as { problemStatement?: string } | null)?.problemStatement || "Loading problem..."}
              </p>
            </div>

            <div className="flex-1 overflow-y-auto no-scrollbar px-6 py-4 space-y-4 font-body text-sm">
              {messages.length === 0 && (
                <div className="h-full flex items-center justify-center text-outline text-sm">
                  Loading session…
                </div>
              )}
              {messages.map((msg, i) => (
                <div key={i} className={cn("flex", msg.role === "user" ? "justify-end" : "justify-start")}>
                  <div
                    className={cn(
                      "max-w-[78%] rounded-2xl px-4 py-3 leading-relaxed whitespace-pre-wrap text-sm",
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

            <div className="border-t border-border bg-surface-container-low shrink-0">
              <div className="flex items-end gap-2 p-4">
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
                    <span className="material-symbols-outlined text-sm animate-spin">progress_activity</span>
                  ) : (
                    <span className="material-symbols-outlined text-sm">send</span>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {showClosingPrompt && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-xl rounded-2xl border border-outline-variant/30 bg-surface-container p-5 space-y-4">
            <h3 className="text-lg font-bold text-on-surface">Before you finish</h3>
            <p className="text-sm text-on-surface-variant leading-relaxed">
              Before you finish — do you have any questions for the interviewer? Asking thoughtful questions about the team, role, or what they care about is part of the interview and will affect your score.
            </p>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setShowClosingPrompt(false)
                  inputRef.current?.focus()
                }}
                className="px-3 py-2 text-xs font-semibold rounded-lg border border-outline-variant/30 text-on-surface-variant hover:bg-surface-container-high transition-colors"
              >
                I have questions
              </button>
              <button
                type="button"
                onClick={handleFinishConfirmed}
                className="px-3 py-2 text-xs font-semibold rounded-lg shimmer-gradient text-on-primary hover:opacity-90 transition-opacity"
              >
                I'm done — score me
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
