import { useEffect, useRef, useState } from "react"
import { useLocation, useNavigate, useParams } from "react-router-dom"
import Editor from "@monaco-editor/react"
import {
  api,
  streamMessage,
  type RunResult,
  type Session,
  type TestResult,
} from "@/lib/api/client"
import { cn } from "@/lib/utils"
import { Sidebar } from "@/components/Sidebar"
import { useSpeechRecognition } from "@/lib/hooks/useSpeechRecognition"

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

function useDraggable(initialPos: { x: number; y: number }) {
  const [pos, setPos] = useState(initialPos)
  const dragging = useRef(false)
  const offset = useRef({ x: 0, y: 0 })
  const posRef = useRef(initialPos)
  posRef.current = pos

  function onMouseDown(e: React.MouseEvent) {
    dragging.current = true
    offset.current = { x: e.clientX - posRef.current.x, y: e.clientY - posRef.current.y }
    e.preventDefault()
  }

  function onTouchStart(e: React.TouchEvent) {
    const touch = e.touches[0]
    dragging.current = true
    offset.current = { x: touch.clientX - posRef.current.x, y: touch.clientY - posRef.current.y }
  }

  const handleMove = (x: number, y: number) => {
    if (!dragging.current) return
    setPos({ x: x - offset.current.x, y: y - offset.current.y })
  }

  const stopDragging = () => { dragging.current = false }

  return { pos, onMouseDown, onTouchStart, handleMove, stopDragging }
}

export default function SessionPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const sessionId = Number(id)
  const timer = useTimer()
  const pip = useDraggable({ x: window.innerWidth - 280, y: 80 })

  const [session, setSession] = useState<Session | null>(null)
  const [problemStatement, setProblemStatement] = useState("")
  const [problemCollapsed, setProblemCollapsed] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [finishing, setFinishing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [code, setCode] = useState("")
  const [runResult, setRunResult] = useState<RunResult | null>(null)
  const [testResult, setTestResult] = useState<TestResult | null>(null)
  const [terminalTab, setTerminalTab] = useState<"console" | "tests">("console")
  const [running, setRunning] = useState(false)
  const [showClosingPrompt, setShowClosingPrompt] = useState(false)
  const [audioEnabled, setAudioEnabled] = useState(false)
  const [avatarSpeaking, setAvatarSpeaking] = useState(false)
  const [voiceName, setVoiceName] = useState<
    "en-US-GuyNeural" | "en-US-JennyNeural" | "en-US-AriaNeural"
  >("en-US-GuyNeural")

  const {
    transcript,
    isListening,
    start: startListening,
    stop: stopListening,
    isSupported: isSpeechSupported,
  } = useSpeechRecognition()

  const activeAudioRef = useRef<HTMLAudioElement | null>(null)
  const pendingTranscriptRef = useRef("")
  const hasPlayedOpeningRef = useRef(false)

  // Load session
  useEffect(() => {
    api.getSession(sessionId).then((s) => {
      setSession(s)
      const navState = location.state as { openingMessage?: string; starterCode?: string; problemStatement?: string } | null
      const starterFromNav = navState?.starterCode
      const problemFromNav = navState?.problemStatement
      if (s.problem_statement) {
        setProblemStatement(s.problem_statement)
      } else if (problemFromNav) {
        setProblemStatement(problemFromNav)
      }
      if (s.starter_code) {
        setCode(s.starter_code)
      } else if (starterFromNav) {
        setCode(starterFromNav)
      }
    })
  }, [sessionId, location.state])

  // Load settings
  useEffect(() => {
    try {
      const raw = localStorage.getItem("grillme_settings")
      if (!raw) return
      const parsed = JSON.parse(raw) as {
        voiceOutputEnabled?: boolean
        voiceName?: "en-US-GuyNeural" | "en-US-JennyNeural" | "en-US-AriaNeural"
      }
      setAudioEnabled(Boolean(parsed.voiceOutputEnabled))
      if (parsed.voiceName) setVoiceName(parsed.voiceName)
    } catch { /* ignore */ }
  }, [])

  // Auto-play opening message once when session + audio are ready
  useEffect(() => {
    if (!audioEnabled || !session || hasPlayedOpeningRef.current) return
    hasPlayedOpeningRef.current = true
    void playAssistantAudio()
  }, [session, audioEnabled]) // eslint-disable-line react-hooks/exhaustive-deps

  // Pause mic while avatar speaks/streaming; restart after each phrase (continuous: false)
  useEffect(() => {
    if (!isSpeechSupported) return
    if (avatarSpeaking || streaming) {
      stopListening()
    } else {
      startListening()
    }
  }, [avatarSpeaking, streaming, isSpeechSupported]) // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-send when mic captures speech and goes silent
  useEffect(() => {
    if (isListening) {
      pendingTranscriptRef.current = transcript
      return
    }
    const text = pendingTranscriptRef.current.trim()
    if (!text || streaming || avatarSpeaking) return
    pendingTranscriptRef.current = ""
    void handleSend(text)
  }, [isListening]) // eslint-disable-line react-hooks/exhaustive-deps

  // Cleanup audio on unmount
  useEffect(() => {
    return () => {
      if (activeAudioRef.current) {
        activeAudioRef.current.pause()
        activeAudioRef.current = null
      }
    }
  }, [])

  async function playAssistantAudio() {
    if (!audioEnabled) return
    try {
      const blob = await api.speakSession(sessionId, voiceName)
      if (activeAudioRef.current) activeAudioRef.current.pause()
      const url = URL.createObjectURL(blob)
      const audio = new Audio(url)
      activeAudioRef.current = audio
      setAvatarSpeaking(true)
      audio.onended = () => { URL.revokeObjectURL(url); setAvatarSpeaking(false) }
      audio.onerror = () => { URL.revokeObjectURL(url); setAvatarSpeaking(false) }
      await audio.play()
    } catch {
      setAvatarSpeaking(false)
    }
  }

  async function handleRunCode() {
    if (!code.trim()) return
    setRunning(true)
    setTerminalTab("console")
    try {
      const result = await api.runCode(code)
      setRunResult(result)
      api.shareCode(sessionId, code, result, undefined).catch(() => {})
    } catch (e) {
      setRunResult({ stdout: "", stderr: e instanceof Error ? e.message : "Error", exit_code: -1, runtime_ms: 0, timed_out: false })
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
    if (e.shiftKey) void handleRunTests()
    else void handleRunCode()
  }

  async function handleSend(text: string) {
    if (!text || streaming) return
    setStreaming(true)
    setError(null)
    try {
      // consume stream but don't display chat
      for await (const _ of streamMessage(sessionId, text)) { /* voice only */ }
      await playAssistantAudio()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Stream error")
    } finally {
      setStreaming(false)
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
            <span className="material-symbols-outlined text-tertiary text-lg" style={{ fontVariationSettings: "'FILL' 1" }}>timer</span>
            <span className="font-mono text-sm font-bold tracking-tight text-on-surface">{timer}</span>
          </div>
          <button
            type="button"
            onClick={() => {
              if (audioEnabled && activeAudioRef.current) {
                activeAudioRef.current.pause()
                activeAudioRef.current = null
                setAvatarSpeaking(false)
              }
              setAudioEnabled((prev) => {
                const next = !prev
                try {
                  const raw = localStorage.getItem("grillme_settings")
                  const current = raw ? JSON.parse(raw) : {}
                  localStorage.setItem("grillme_settings", JSON.stringify({ ...current, voiceOutputEnabled: next }))
                } catch { /* ignore */ }
                return next
              })
            }}
            className={cn(
              "px-3 py-1.5 text-xs font-bold rounded-xl border transition-colors",
              audioEnabled ? "border-primary/40 bg-primary/15 text-primary" : "border-outline-variant/30 bg-surface-container-highest text-on-surface-variant hover:text-on-surface",
            )}
          >
            Audio {audioEnabled ? "On" : "Off"}
          </button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <Sidebar activePage="home" />

        <div className="flex flex-1 overflow-hidden">
          {/* LEFT — collapsible problem statement */}
          <div className="w-2/5 border-r border-border bg-surface-container-low flex flex-col overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2 bg-surface-container-low border-b border-border shrink-0">
              <button
                onClick={() => setProblemCollapsed((c) => !c)}
                className="flex items-center gap-2"
              >
                <span className="material-symbols-outlined text-primary text-base" style={{ fontVariationSettings: "'FILL' 1" }}>
                  {problemCollapsed ? "chevron_right" : "expand_more"}
                </span>
                <span className="text-xs font-bold text-on-surface uppercase tracking-widest">Coding Problem</span>
              </button>
              {session?.difficulty && (
                <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-primary/10 text-primary border border-primary/30">
                  {session.difficulty}
                </span>
              )}
            </div>

            {!problemCollapsed && (
              <div className="flex-1 overflow-y-auto no-scrollbar p-4">
                <p className="text-sm text-on-surface whitespace-pre-wrap leading-relaxed">
                  {problemStatement || (location.state as { problemStatement?: string } | null)?.problemStatement || "Loading problem..."}
                </p>
              </div>
            )}

            {error && (
              <div className="mx-4 mb-3 flex items-center gap-2 text-error text-xs px-3 py-2 bg-error-container/10 rounded-xl border border-error/20 shrink-0">
                <span className="material-symbols-outlined text-sm">error</span>
                {error}
              </div>
            )}

            {/* Live transcript */}
            <div className="px-4 py-3 border-t border-border shrink-0 min-h-[52px] flex items-center">
              {isListening && transcript ? (
                <p className="text-xs text-blue-300 italic leading-relaxed line-clamp-2">"{transcript}"</p>
              ) : isListening ? (
                <div className="flex items-center gap-2">
                  {[0, 100, 200].map((delay) => (
                    <div key={delay} className="w-0.5 rounded-full bar-wave bg-blue-400/60" style={{ animationDelay: `${delay}ms`, height: "8px" }} />
                  ))}
                  <span className="text-xs text-blue-400/60">Listening…</span>
                </div>
              ) : streaming ? (
                <span className="text-xs text-on-surface-variant/60">Thinking…</span>
              ) : (
                <span className="text-xs text-outline/30">Speak to respond</span>
              )}
            </div>
          </div>

          {/* RIGHT — Monaco editor + console + Finish button */}
          <div className="flex-1 flex flex-col bg-surface-container-lowest overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2 bg-surface-container-low border-b border-border shrink-0">
              <div className="flex items-center gap-2 px-3 py-1 bg-surface-container-highest rounded-lg text-xs font-semibold text-on-surface border border-outline-variant/20">
                <span className="w-2 h-2 rounded-full bg-blue-400" />
                Python 3.13
              </div>
              <div className="flex gap-2">
                <button onClick={handleRunCode} disabled={running || !code.trim()} className="px-3 py-1 text-xs font-semibold rounded-lg bg-surface-container-highest text-on-surface-variant hover:bg-surface-bright transition-colors disabled:opacity-40">
                  Run Code
                </button>
                <button onClick={handleRunTests} disabled={running || !code.trim() || !session?.test_cases} className="px-3 py-1 text-xs font-semibold rounded-lg bg-primary/20 text-primary hover:bg-primary/30 transition-colors disabled:opacity-40">
                  Run Tests
                </button>
                <button
                  className="px-3 py-1 text-xs font-bold rounded-lg bg-surface-container-highest text-on-surface hover:bg-surface-bright transition-colors active:scale-[0.97] disabled:opacity-40"
                  onClick={handleFinishClick}
                  disabled={finishing}
                >
                  {finishing ? <span className="material-symbols-outlined text-sm animate-spin">progress_activity</span> : "Finish & Score"}
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
                  options={{ fontSize: 13, minimap: { enabled: false }, lineNumbers: "on", scrollBeyondLastLine: false, automaticLayout: true }}
                />
              </div>
            </div>

            <div className="flex-1 flex flex-col min-h-0">
              <div className="flex items-center gap-3 px-4 py-1.5 border-b border-border bg-surface-container-low shrink-0">
                <button className={cn("text-[10px] font-bold uppercase tracking-widest", terminalTab === "console" ? "text-primary border-b border-primary" : "text-outline hover:text-on-surface")} onClick={() => setTerminalTab("console")}>Console</button>
                <button className={cn("text-[10px] font-bold uppercase tracking-widest", terminalTab === "tests" ? "text-primary border-b border-primary" : "text-outline hover:text-on-surface")} onClick={() => setTerminalTab("tests")}>Test Results</button>
              </div>
              <div className="flex-1 overflow-y-auto no-scrollbar p-4 font-mono text-xs">
                {terminalTab === "console" ? (
                  runResult ? (
                    <div className="space-y-2">
                      {runResult.timed_out && <div className="rounded-md border border-yellow-500/40 bg-yellow-500/10 px-2 py-1 text-yellow-300">Execution timed out (10s limit)</div>}
                      {runResult.stdout && <pre className="whitespace-pre-wrap text-on-surface">{runResult.stdout}</pre>}
                      {runResult.stderr && <pre className="whitespace-pre-wrap text-error">{runResult.stderr}</pre>}
                      {!runResult.stdout && !runResult.stderr && <p className="text-outline">No output.</p>}
                      <p className="text-on-surface-variant">Exit: {runResult.exit_code} · {runResult.runtime_ms}ms</p>
                    </div>
                  ) : <p className="text-outline">Run your code to see output</p>
                ) : testResult ? (
                  <div className="space-y-2">
                    <p className="text-on-surface-variant font-semibold">{testResult.passed}/{testResult.total} passed · {testResult.runtime_ms}ms</p>
                    {testResult.results.map((r) => (
                      <div key={r.id} className={cn("rounded-md px-2 py-1", r.passed ? "bg-green-500/10" : "bg-red-500/10")}>
                        <p className={cn("font-semibold", r.passed ? "text-green-400" : "text-red-400")}>{r.passed ? "✓" : "✗"} Test {r.id}</p>
                        {r.error ? <p className="text-red-400">input={r.input} → error: {r.error}</p> : <p className="text-on-surface-variant">input={r.input} → expected {r.expected}, got {r.actual}</p>}
                      </div>
                    ))}
                  </div>
                ) : <p className="text-outline">Run tests to see results</p>}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Floating PIP — same position as Home */}
      <div
        className="fixed z-50 w-64 rounded-2xl overflow-hidden glass-panel shadow-2xl select-none"
        style={{ left: pip.pos.x, top: pip.pos.y }}
        onMouseMove={(e) => pip.handleMove(e.clientX, e.clientY)}
        onMouseUp={pip.stopDragging}
        onMouseLeave={pip.stopDragging}
        onTouchMove={(e) => { const t = e.touches[0]; pip.handleMove(t.clientX, t.clientY) }}
        onTouchEnd={pip.stopDragging}
      >
        <div
          className="flex items-center justify-between px-3 py-2 bg-surface-container/90 cursor-grab active:cursor-grabbing border-b border-white/5"
          onMouseDown={pip.onMouseDown}
          onTouchStart={pip.onTouchStart}
        >
          <div className="flex items-center gap-2">
            <div className={cn("w-1.5 h-1.5 rounded-full animate-pulse", avatarSpeaking ? "bg-primary" : isListening ? "bg-blue-400" : "bg-outline/40")} />
            <span className="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">AI Interviewer</span>
          </div>
          <div className="flex items-end gap-0.5">
            {(avatarSpeaking || isListening) && (avatarSpeaking ? [0, 120, 240, 360, 480] : [0, 150, 300]).map((delay) => (
              <div key={delay} className={cn("w-0.5 rounded-full bar-wave", avatarSpeaking ? "bg-primary" : "bg-blue-400")} style={{ animationDelay: `${delay}ms`, height: "8px" }} />
            ))}
          </div>
        </div>
        <div className="relative bg-surface-container-low" style={{ aspectRatio: "4/3" }}>
          <div className="w-full h-full flex flex-col items-center justify-center gap-2 bg-gradient-to-br from-surface-container to-surface-container-highest">
            <span
              className="material-symbols-outlined text-7xl pip-idle transition-all duration-500"
              style={{
                fontVariationSettings: avatarSpeaking ? "'FILL' 1" : "'FILL' 0",
                color: avatarSpeaking
                  ? "rgba(224,90,58,0.9)"
                  : isListening
                  ? "rgba(96,165,250,0.85)"
                  : "rgba(155,156,158,0.3)",
              }}
            >
              {avatarSpeaking ? "record_voice_over" : "face"}
            </span>
            <span
              className="text-[10px] uppercase tracking-widest font-semibold transition-colors duration-300"
              style={{
                color: avatarSpeaking
                  ? "rgba(224,90,58,0.7)"
                  : isListening
                  ? "rgba(96,165,250,0.6)"
                  : audioEnabled
                  ? "rgba(155,156,158,0.3)"
                  : "rgba(155,156,158,0.25)",
              }}
            >
              {avatarSpeaking ? "Speaking" : isListening ? "Listening" : audioEnabled ? "Ready" : "Audio off"}
            </span>
          </div>
          {(avatarSpeaking || isListening) && (
            <span className={cn("absolute inset-0 animate-ping opacity-10", avatarSpeaking ? "bg-primary" : "bg-blue-400")} />
          )}
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
              <button type="button" onClick={() => setShowClosingPrompt(false)} className="px-3 py-2 text-xs font-semibold rounded-lg border border-outline-variant/30 text-on-surface-variant hover:bg-surface-container-high transition-colors">
                I have questions
              </button>
              <button type="button" onClick={handleFinishConfirmed} className="px-3 py-2 text-xs font-semibold rounded-lg shimmer-gradient text-on-primary hover:opacity-90 transition-opacity">
                I'm done — score me
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
