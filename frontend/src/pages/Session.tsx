import { useEffect, useRef, useState } from "react"
import { Link, useLocation, useNavigate, useParams } from "react-router-dom"
import Editor from "@monaco-editor/react"
import {
  api,
  streamMessage,
  type AvatarSessionInfo,
  type RunResult,
  type Session,
  type TestResult,
} from "@/lib/api/client"
import { cn } from "@/lib/utils"
import { Sidebar } from "@/components/Sidebar"
import { Avatar } from "@/components/Avatar"
import { useSpeechRecognition } from "@/lib/hooks/useSpeechRecognition"

type DialogueTurn = {
  id: string
  role: "assistant" | "user"
  text: string
}

function inferVoiceFromPersona(personaText?: string | null): "en-US-GuyNeural" | "en-US-JennyNeural" | "en-US-AriaNeural" {
  const raw = (personaText ?? "").toLowerCase()
  if (!raw) return "en-US-JennyNeural"
  const femaleSignals = [
    " she ",
    " her ",
    "herself",
    " rachel",
    " emma",
    " sophia",
    " olivia",
    " jenny",
    " aria",
  ]
  const normalized = ` ${raw.replace(/[^\w\s]/g, " ")} `
  if (femaleSignals.some((sig) => normalized.includes(sig))) return "en-US-JennyNeural"
  return "en-US-GuyNeural"
}

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

  useEffect(() => {
    const onWindowMouseMove = (e: MouseEvent) => {
      handleMove(e.clientX, e.clientY)
    }
    const onWindowMouseUp = () => {
      stopDragging()
    }
    const onWindowTouchMove = (e: TouchEvent) => {
      const touch = e.touches[0]
      if (!touch) return
      handleMove(touch.clientX, touch.clientY)
    }
    const onWindowTouchEnd = () => {
      stopDragging()
    }

    window.addEventListener("mousemove", onWindowMouseMove)
    window.addEventListener("mouseup", onWindowMouseUp)
    window.addEventListener("touchmove", onWindowTouchMove, { passive: true })
    window.addEventListener("touchend", onWindowTouchEnd)

    return () => {
      window.removeEventListener("mousemove", onWindowMouseMove)
      window.removeEventListener("mouseup", onWindowMouseUp)
      window.removeEventListener("touchmove", onWindowTouchMove)
      window.removeEventListener("touchend", onWindowTouchEnd)
    }
  }, [])

  return { pos, onMouseDown, onTouchStart, stopDragging }
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
  const [audioEnabled, setAudioEnabled] = useState(true)
  const [avatarSpeaking, setAvatarSpeaking] = useState(false)
  const [voiceName, setVoiceName] = useState<
    "en-US-GuyNeural" | "en-US-JennyNeural" | "en-US-AriaNeural"
  >("en-US-GuyNeural")
  const [dialogue, setDialogue] = useState<DialogueTurn[]>([])
  const [latestReply, setLatestReply] = useState("")
  const [voiceNeedsUnlock, setVoiceNeedsUnlock] = useState(false)
  const [turnState, setTurnState] = useState<"idle" | "listening" | "thinking" | "speaking">("idle")
  const [leftPaneWidth, setLeftPaneWidth] = useState(40)
  const [avatarSession, setAvatarSession] = useState<AvatarSessionInfo>({
    enabled: false,
    provider: "local",
    persona_seed: "default",
  })
  const [avatarVideoUrl, setAvatarVideoUrl] = useState<string | null>(null)

  const {
    transcript,
    isListening,
    start: startListening,
    stop: stopListening,
    isSupported: isSpeechSupported,
  } = useSpeechRecognition()

  const activeAudioRef = useRef<HTMLAudioElement | null>(null)
  const audioContextRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const playbackRef = useRef<{
    url: string
    source: MediaElementAudioSourceNode
    analyser: AnalyserNode
  } | null>(null)
  const pendingSpeechRef = useRef<string | null>(null)
  const pendingTranscriptRef = useRef("")
  const lastSentTranscriptRef = useRef("")
  const hasPlayedOpeningRef = useRef(false)
  const dialogueRef = useRef<HTMLDivElement | null>(null)
  const editorLayoutRef = useRef<HTMLDivElement | null>(null)
  const resizingPanelsRef = useRef(false)
  const avatarVideoRequestRef = useRef(0)
  const explicitVoicePreferenceRef = useRef(false)

  function buildDialogue(messages: Session["messages"]): DialogueTurn[] {
    return messages
      .filter((m) => m.role === "assistant" || m.role === "user")
      .map((m, idx) => ({
        id: `${m.role}-${idx}`,
        role: m.role as "assistant" | "user",
        text: m.content,
      }))
  }

  useEffect(() => {
    Promise.all([
      api.getSession(sessionId),
      api.getAvatarSession(sessionId).catch(() => ({
        enabled: false,
        provider: "local" as const,
        persona_seed: "default",
      })),
    ]).then(([s, avatar]) => {
      setSession(s)
      setAvatarSession(avatar)
      if (!explicitVoicePreferenceRef.current) {
        setVoiceName(inferVoiceFromPersona(s.persona))
      }
      const navState = location.state as { starterCode?: string; problemStatement?: string } | null
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

      const turns = buildDialogue(s.messages)
      setDialogue(turns)
    })
  }, [sessionId, location.state])

  useEffect(() => {
    try {
      const raw = localStorage.getItem("grillme_settings")
      if (!raw) {
        setAudioEnabled(true)
        return
      }
      const parsed = JSON.parse(raw) as {
        voiceOutputEnabled?: boolean
        voiceName?: "en-US-GuyNeural" | "en-US-JennyNeural" | "en-US-AriaNeural"
      }
      setAudioEnabled(parsed.voiceOutputEnabled ?? true)
      if (parsed.voiceName) {
        explicitVoicePreferenceRef.current = true
        setVoiceName(parsed.voiceName)
      }
    } catch { /* ignore */ }
  }, [])

  useEffect(() => {
    if (avatarSpeaking) {
      setTurnState("speaking")
      return
    }
    if (streaming) {
      setTurnState("thinking")
      return
    }
    if (isListening) {
      setTurnState("listening")
      return
    }
    setTurnState("idle")
  }, [avatarSpeaking, streaming, isListening])

  useEffect(() => {
    const el = dialogueRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
  }, [dialogue, latestReply])

  useEffect(() => {
    if (!audioEnabled || !session || hasPlayedOpeningRef.current) return
    hasPlayedOpeningRef.current = true
    void playAssistantAudio()
  }, [audioEnabled, session]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!isSpeechSupported) return
    if (avatarSpeaking || streaming || (audioEnabled && voiceNeedsUnlock)) {
      stopListening()
      return
    }
    if (!isListening) startListening()
  }, [avatarSpeaking, streaming, voiceNeedsUnlock, audioEnabled, isSpeechSupported, isListening]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!isListening || !transcript.trim()) return
    pendingTranscriptRef.current = transcript
  }, [isListening, transcript])

  useEffect(() => {
    if (isListening || streaming) return
    const text = pendingTranscriptRef.current.trim()
    if (!text || avatarSpeaking) return
    if (text === lastSentTranscriptRef.current) return
    lastSentTranscriptRef.current = text
    pendingTranscriptRef.current = ""
    void handleSend(text)
  }, [isListening, avatarSpeaking, streaming]) // eslint-disable-line react-hooks/exhaustive-deps

  function cleanupActiveAudio() {
    if (activeAudioRef.current) {
      activeAudioRef.current.onended = null
      activeAudioRef.current.onerror = null
      activeAudioRef.current.pause()
      activeAudioRef.current = null
    }
    if (playbackRef.current) {
      URL.revokeObjectURL(playbackRef.current.url)
      playbackRef.current.source.disconnect()
      playbackRef.current.analyser.disconnect()
      playbackRef.current = null
    }
    analyserRef.current = null
    setAvatarSpeaking(false)
  }

  useEffect(() => {
    return () => {
      cleanupActiveAudio()
      if (audioContextRef.current) {
        void audioContextRef.current.close()
      }
    }
  }, [])

  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (!resizingPanelsRef.current || !editorLayoutRef.current) return
      const rect = editorLayoutRef.current.getBoundingClientRect()
      if (rect.width <= 0) return
      const next = ((e.clientX - rect.left) / rect.width) * 100
      setLeftPaneWidth(Math.max(30, Math.min(55, next)))
    }
    const onMouseUp = () => {
      resizingPanelsRef.current = false
    }
    window.addEventListener("mousemove", onMouseMove)
    window.addEventListener("mouseup", onMouseUp)
    return () => {
      window.removeEventListener("mousemove", onMouseMove)
      window.removeEventListener("mouseup", onMouseUp)
    }
  }, [])

  async function playAssistantAudio(text?: string): Promise<boolean> {
    if (!audioEnabled) return true
    const speechText = text?.trim() ? text : undefined
    if (speechText && avatarSession.enabled && avatarSession.provider !== "local") {
      const reqId = ++avatarVideoRequestRef.current
      setAvatarVideoUrl(null)
      api.getAvatarSpeakVideo(sessionId, speechText)
        .then((video) => {
          if (reqId !== avatarVideoRequestRef.current) return
          if (!video.enabled || !video.video_url) return
          setAvatarVideoUrl(video.video_url)
        })
        .catch(() => {})
    }
    try {
      const blob = speechText
        ? await api.speakText(speechText, voiceName)
        : await api.speakSession(sessionId, voiceName)
      cleanupActiveAudio()
      const url = URL.createObjectURL(blob)
      const audio = new Audio(url)
      activeAudioRef.current = audio

      if (!audioContextRef.current) {
        audioContextRef.current = new AudioContext()
      }
      if (audioContextRef.current.state === "suspended") {
        await audioContextRef.current.resume()
      }
      const source = audioContextRef.current.createMediaElementSource(audio)
      const analyser = audioContextRef.current.createAnalyser()
      analyser.fftSize = 256
      source.connect(analyser)
      analyser.connect(audioContextRef.current.destination)
      analyserRef.current = analyser
      playbackRef.current = { url, source, analyser }
      setAvatarSpeaking(true)

      audio.onended = () => {
        cleanupActiveAudio()
      }
      audio.onerror = () => {
        cleanupActiveAudio()
      }

      await audio.play()
      pendingSpeechRef.current = null
      setVoiceNeedsUnlock(false)
      return true
    } catch {
      setAvatarSpeaking(false)
      pendingSpeechRef.current = speechText ?? "__session_opening__"
      setVoiceNeedsUnlock(true)
      return false
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
    setLatestReply("Thinking…")
    setDialogue((prev) => [
      ...prev,
      { id: `user-${Date.now()}`, role: "user", text },
    ])
    try {
      let accumulatedText = ""
      for await (const chunk of streamMessage(sessionId, text)) {
        accumulatedText += chunk
        setLatestReply(accumulatedText)
      }
      setLatestReply(accumulatedText)
      setDialogue((prev) => [
        ...prev,
        { id: `assistant-${Date.now()}`, role: "assistant", text: accumulatedText },
      ])
      setLatestReply("")
      await playAssistantAudio(accumulatedText)
    } catch (e) {
      setLatestReply("")
      setError(e instanceof Error ? e.message : "Stream error")
    } finally {
      setStreaming(false)
    }
  }

  function handleEnableVoicePlayback() {
    const pending = pendingSpeechRef.current
    if (!pending) return
    if (pending === "__session_opening__") {
      void playAssistantAudio()
      return
    }
    void playAssistantAudio(pending)
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

  const streamingReply = latestReply === "Thinking…" ? "" : latestReply
  const statusLabel = turnState === "speaking"
    ? "Speaking"
    : turnState === "thinking"
      ? "Thinking"
      : turnState === "listening"
        ? "Listening"
        : audioEnabled
          ? "Ready"
          : "Audio off"

  return (
    <div className="h-screen overflow-hidden flex flex-col bg-background">
      <header className="flex justify-between items-center w-full px-6 py-3 border-b border-border bg-background shrink-0 z-50">
        <Link to="/" className="flex items-center gap-2 hover:opacity-90 transition-opacity">
          <img src="/logo.jpg" alt="grillme" className="h-9 w-9 rounded-full" />
          <span className="text-xl font-black tracking-tighter uppercase font-wordmark">
            <span className="text-on-surface">grill</span>
            <span className="text-primary">me</span>
          </span>
        </Link>
        <div className="flex items-center gap-4 ml-auto">
          <div className="flex items-center gap-2 bg-surface-container-low px-3 py-1.5 rounded-xl border border-outline-variant/20">
            <span className="material-symbols-outlined text-tertiary text-lg" style={{ fontVariationSettings: "'FILL' 1" }}>timer</span>
            <span className="font-mono text-sm font-bold tracking-tight text-on-surface">{timer}</span>
          </div>
          <button
            type="button"
            onClick={() => {
              if (audioEnabled && activeAudioRef.current) {
                cleanupActiveAudio()
              }
              setVoiceNeedsUnlock(false)
              pendingSpeechRef.current = null
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

        <div ref={editorLayoutRef} className="flex flex-1 overflow-hidden">
          <div style={{ width: `${leftPaneWidth}%` }} className="border-r border-border bg-surface-container-low flex flex-col overflow-hidden">
            <div className="border-b border-border bg-surface-container-low shrink-0">
              <div className="px-4 py-2 flex items-center justify-between">
                <button
                  onClick={() => setProblemCollapsed((c) => !c)}
                  className="flex items-center gap-2 text-left"
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
                <div className="px-4 pb-3 max-h-52 overflow-y-auto no-scrollbar">
                  <p className="text-xs text-on-surface whitespace-pre-wrap leading-relaxed">
                    {problemStatement || (location.state as { problemStatement?: string } | null)?.problemStatement || "Loading problem..."}
                  </p>
                </div>
              )}
            </div>

            <div className="px-4 py-2 border-b border-border shrink-0">
              <span className="text-[11px] font-bold text-on-surface uppercase tracking-widest">Interview Dialogue</span>
            </div>

            <div ref={dialogueRef} className="flex-1 overflow-y-auto no-scrollbar p-3 space-y-2">
              {dialogue.length === 0 && !streamingReply ? (
                <p className="text-xs italic text-on-surface-variant/60">Interview conversation will appear here.</p>
              ) : (
                <>
                  {dialogue.map((turn) => (
                    <div
                      key={turn.id}
                      className={cn(
                        "max-w-[92%] rounded-lg px-2.5 py-2 text-xs leading-relaxed whitespace-pre-wrap",
                        turn.role === "assistant"
                          ? "mr-auto bg-surface-container text-on-surface border border-outline-variant/20"
                          : "ml-auto bg-primary/10 border border-primary/30 text-on-surface",
                      )}
                    >
                      <span className={cn("mb-1 block text-[10px] font-bold uppercase tracking-widest", turn.role === "assistant" ? "text-primary/80" : "text-blue-300/90")}>
                        {turn.role === "assistant" ? "Interviewer" : "You"}
                      </span>
                      {turn.text}
                    </div>
                  ))}
                  {(streaming || streamingReply) && (
                    <div className="max-w-[92%] mr-auto rounded-lg px-2.5 py-2 text-xs leading-relaxed whitespace-pre-wrap bg-surface-container text-on-surface border border-outline-variant/20">
                      <span className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-primary/80">Interviewer</span>
                      {latestReply}
                    </div>
                  )}
                </>
              )}
            </div>

            {error && (
              <div className="mx-4 mb-3 flex items-center gap-2 text-error text-xs px-3 py-2 bg-error-container/10 rounded-xl border border-error/20 shrink-0">
                <span className="material-symbols-outlined text-sm">error</span>
                {error}
              </div>
            )}

            <div className="px-4 py-3 border-t border-border shrink-0 min-h-[52px] flex items-center justify-between gap-3">
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
              <div className="flex items-center gap-2 shrink-0">
                {voiceNeedsUnlock && audioEnabled && (
                  <button
                    type="button"
                    onClick={handleEnableVoicePlayback}
                    className="px-2 py-1 text-[10px] font-semibold rounded-md border border-primary/40 bg-primary/10 text-primary hover:bg-primary/20"
                  >
                    Enable voice
                  </button>
                )}
                <span className="text-[10px] uppercase tracking-widest text-on-surface-variant/70">
                  {turnState}
                </span>
              </div>
            </div>
          </div>

          <div
            className="w-1.5 bg-border/70 hover:bg-primary/60 cursor-col-resize shrink-0 transition-colors"
            onMouseDown={() => { resizingPanelsRef.current = true }}
          />

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

      <Avatar
        speaking={avatarSpeaking}
        listening={isListening}
        audioEnabled={audioEnabled}
        statusLabel={statusLabel}
        pos={pip.pos}
        personaText={session?.persona ?? undefined}
        provider={avatarSession.provider}
        personaSeed={avatarSession.persona_seed}
        videoUrl={avatarVideoUrl}
        analyserRef={analyserRef}
        onMouseDown={pip.onMouseDown}
        onTouchStart={pip.onTouchStart}
      />

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
