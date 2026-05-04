import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import ReactMarkdown from "react-markdown"
import { Link, useLocation, useNavigate, useParams } from "react-router-dom"
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
import { useVAD, encodeWAV } from "@/lib/hooks/useVAD"
import { usePushToTalk } from "@/lib/hooks/usePushToTalk"

// ── Types ─────────────────────────────────────────────────────────────────────

type DialogueTurn = {
  id: string
  role: "assistant" | "user"
  text: string
}

type VoiceTurnState = "idle" | "recording" | "processing" | "rendering" | "speaking"

// ── Helpers ───────────────────────────────────────────────────────────────────

const PHOTO = {
  m: "/interviewer.jpg",
  f: "/interviewer-f.jpg",
} as const

const AVATAR_MEDIA_CLASS = "absolute inset-0 w-full h-full object-cover object-top"
const PIP_WIDTH_PX = 128
const PIP_RIGHT_MARGIN_PX = 72

function extractName(text?: string): string {
  if (!text?.trim()) return "AI Interviewer"
  const m =
    text.match(/(?:name is|I am|I'm)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)/) ??
    text.match(/\b([A-Z][a-z]{2,})\b/)
  return m?.[1] ?? "AI Interviewer"
}


function useTimer(sessionId: number, initialSeconds = 60 * 60) {
  const storageKey = `grillme_timer_start_${sessionId}`

  // On mount, read the stored start time or record now
  const [seconds, setSeconds] = useState(() => {
    const stored = sessionStorage.getItem(storageKey)
    if (stored) {
      const startedAt = parseInt(stored, 10)
      const elapsed = Math.floor((Date.now() - startedAt) / 1000)
      return Math.max(0, initialSeconds - elapsed)
    }
    sessionStorage.setItem(storageKey, String(Date.now()))
    return initialSeconds
  })

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
  }
  const onTouchStart = (e: React.TouchEvent) => {
    const t = e.touches[0]
    dragging.current = true
    offset.current = { x: t.clientX - posRef.current.x, y: t.clientY - posRef.current.y }
  }
  useEffect(() => {
    const mm = (e: MouseEvent) => { if (dragging.current) setPos({ x: e.clientX - offset.current.x, y: e.clientY - offset.current.y }) }
    const mu = () => { dragging.current = false }
    const tm = (e: TouchEvent) => { const t = e.touches[0]; if (t && dragging.current) setPos({ x: t.clientX - offset.current.x, y: t.clientY - offset.current.y }) }
    window.addEventListener("mousemove", mm); window.addEventListener("mouseup", mu)
    window.addEventListener("touchmove", tm, { passive: true }); window.addEventListener("touchend", mu)
    return () => { window.removeEventListener("mousemove", mm); window.removeEventListener("mouseup", mu); window.removeEventListener("touchmove", tm); window.removeEventListener("touchend", mu) }
  }, [])
  return { pos, onMouseDown, onTouchStart }
}

// ════════════════════════════════════════════════════════════════════════════

export default function SessionPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const sessionId = Number(id)
  const timer = useTimer(sessionId)
  const pip = useDraggable({ x: window.innerWidth - (PIP_WIDTH_PX + PIP_RIGHT_MARGIN_PX), y: 80 })

  // ── Eagerly request mic permission on mount ───────────────────────────────
  // This makes the OS mic indicator appear immediately so the user knows
  // the app will use the mic. The stream is released right away — actual
  // recording happens via PTT (MediaRecorder) or VAD (MicVAD) separately.
  const [micError, setMicError] = useState<string | null>(null)
  useEffect(() => {
    navigator.mediaDevices?.getUserMedia({ audio: true })
      .then((stream) => {
        stream.getTracks().forEach((t) => t.stop())  // release immediately
      })
      .catch((err: unknown) => {
        const name = err instanceof Error ? err.name : ""
        if (name === "NotAllowedError" || name === "PermissionDeniedError") {
          setMicError("Microphone permission denied. Allow mic access in browser settings, then reload the page.")
        }
      })
  }, [])

  // ── Core state ────────────────────────────────────────────────────────────
  const [session, setSession] = useState<Session | null>(null)
  const [problemStatement, setProblemStatement] = useState("")
  const [problemCollapsed, setProblemCollapsed] = useState(false)
  const [problemReady, setProblemReady] = useState(false)
  const [finishing, setFinishing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [code, setCode] = useState("")
  const [runResult, setRunResult] = useState<RunResult | null>(null)
  const [testResult, setTestResult] = useState<TestResult | null>(null)
  const [terminalTab, setTerminalTab] = useState<"console" | "tests">("console")
  const [running, setRunning] = useState(false)
  const [showClosingPrompt, setShowClosingPrompt] = useState(false)
  const [leftPaneWidth, setLeftPaneWidth] = useState(40)
  const [dialogue, setDialogue] = useState<DialogueTurn[]>([])
  const [latestReply, setLatestReply] = useState("")

  // ── Voice state ───────────────────────────────────────────────────────────
  const [turnState, setTurnState] = useState<VoiceTurnState>("idle")
  // VAD must not start until opening audio finishes — rapid enable/disable
  // during session load crashes the AudioWorklet
  const [openingDone, setOpeningDone] = useState(false)
  const [transcribedText, setTranscribedText] = useState("")

  // ── Input mode ───────────────────────────────────────────────────────────
  const pttSupported = typeof MediaRecorder !== "undefined"

  // ── Avatar video/audio state ──────────────────────────────────────────────
  // activeVideo: wav2lip MP4 url (intro + conversation)
  // activeAudio: TTS mp3 blob url (conversation fallback while wav2lip renders)
  const [activeVideo, setActiveVideo] = useState<string | null>(null)
  const [activeAudio, setActiveAudio] = useState<string | null>(null)
  // showPhoto: true when video finished — controls fade-in of photo
  const [showPhoto, setShowPhoto] = useState(true)
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  // Imperatively play audio when src changes — autoPlay alone doesn't retrigger on src change in React
  useEffect(() => {
    const el = audioRef.current
    if (!el || !activeAudio) return
    el.load()
    el.play().catch(() => {})
  }, [activeAudio])

  // ── Refs ──────────────────────────────────────────────────────────────────
  const hasPlayedOpeningRef = useRef(false)
  const pendingIntroRef = useRef<(() => void) | null>(null)  // queued intro to play after smalltalk
  const dialogueRef = useRef<HTMLDivElement | null>(null)
  const editorLayoutRef = useRef<HTMLDivElement | null>(null)
  const resizingPanelsRef = useRef(false)
  const processingRef = useRef(false)
  const introPollerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const jobPollerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const ttsUrlRef = useRef<string>("")
  const ttsFinishedRef = useRef(false)   // true when TTS audio ended before video arrived
  const turnStateRef = useRef<VoiceTurnState>("idle")
  const thinkingClipsRef = useRef<string[]>([])

  const isSpeaking = turnState === "speaking"
  const isRecording = turnState === "recording"
  const isProcessing = turnState === "processing"
  const isRendering = turnState === "rendering"
  // Keep ref in sync so callbacks can read current turnState without stale closures
  turnStateRef.current = turnState

  const gender = "m"
  const derivedVoice = "en-US-GuyNeural"
  const photoSrc = PHOTO[gender]
  const personaName = extractName(session?.persona ?? undefined)

  const statusLabel = isSpeaking
    ? "Speaking"
    : isRecording
    ? "Listening"
    : isRendering
    ? "Rendering…"
    : isProcessing
    ? "Thinking…"
    : "Ready"

  // ── Helpers ───────────────────────────────────────────────────────────────

  function buildDialogue(messages: Session["messages"]): DialogueTurn[] {
    return messages
      .filter((m) => m.role === "assistant" || m.role === "user")
      .map((m, idx) => ({ id: `${m.role}-${idx}`, role: m.role as "assistant" | "user", text: m.content }))
  }

  // ── TTS-only opening — fallback when no pre-rendered intro clip is available ─
  async function playAudioOpening(sid: number) {
    try {
      const blob = await api.speakSession(sid, derivedVoice)
      const url = URL.createObjectURL(blob)
      setShowPhoto(false)
      setActiveAudio(url)
      setTurnState("speaking")
      setOpeningDone(true)
    } catch {
      setShowPhoto(true)
      setTurnState("idle")
      setOpeningDone(true)
    }
  }

  // ── Ended handlers ────────────────────────────────────────────────────────
  const handleVideoEnded = useCallback(() => {
    if (activeVideo?.startsWith("blob:")) URL.revokeObjectURL(activeVideo)
    setActiveVideo(null)
    setShowPhoto(true)
    setTurnState("idle")
    processingRef.current = false
    if (pendingIntroRef.current) {
      // Intro is queued — 3s pause (photo visible) then play intro
      const play = pendingIntroRef.current
      pendingIntroRef.current = null
      setTimeout(() => play(), 3000)
    } else {
      setOpeningDone(true)  // No more queued content — VAD/PTT safe to start
    }
  }, [activeVideo])

  const handleAudioEnded = useCallback(() => {
    if (activeAudio?.startsWith("blob:")) URL.revokeObjectURL(activeAudio)
    setActiveAudio(null)
    setShowPhoto(true)
    setTurnState("idle")
    setOpeningDone(true)
    processingRef.current = false
    ttsFinishedRef.current = true  // video arrives after this → mute it
  }, [activeAudio])

  // ── Poll a wav2lip response job until done ────────────────────────────────
  // ttsPromise: in-flight TTS fetch — played immediately by processUtterance,
  // stopped when video arrives (Bug 2 fix), or used as fallback on error
  const pollJob = useCallback((jobId: string, ttsPromise: Promise<Blob | null>) => {
    if (jobPollerRef.current) clearInterval(jobPollerRef.current)
    ttsFinishedRef.current = false  // reset for this response turn
    let elapsed = 0

    jobPollerRef.current = setInterval(async () => {
      elapsed += 2
      try {
        const job = await api.getVideoJob(jobId)
        if (job.status === "done" && job.video_url) {
          if (jobPollerRef.current) clearInterval(jobPollerRef.current)
          jobPollerRef.current = null
          // Stop TTS if still playing — video has its own audio
          if (audioRef.current) {
            audioRef.current.pause()
            audioRef.current.src = ""
          }
          setActiveAudio(null)
          if (ttsUrlRef.current) {
            URL.revokeObjectURL(ttsUrlRef.current)
            ttsUrlRef.current = ""
          }
          // Mute video if TTS already finished — user heard the audio, but still
          // show the video so they can see wav2lip is working (lip sync visible)
          if (videoRef.current) {
            videoRef.current.muted = ttsFinishedRef.current
            videoRef.current.volume = ttsFinishedRef.current ? 0 : 1
          }
          setShowPhoto(false)
          setActiveVideo(job.video_url)
          setTurnState("speaking")
        } else if (job.status === "error" || job.status === "not_found" || elapsed >= 120) {
          // wav2lip failed / timed out — fall back to TTS audio
          if (jobPollerRef.current) clearInterval(jobPollerRef.current)
          jobPollerRef.current = null
          // Stop any currently playing TTS first, then restart from blob
          if (audioRef.current) {
            audioRef.current.pause()
            audioRef.current.src = ""
          }
          setActiveAudio(null)
          // Use already-created URL if available, otherwise await the promise
          const fallbackUrl = ttsUrlRef.current || await ttsPromise.then((blob) => {
            if (!blob) return ""
            const url = URL.createObjectURL(blob)
            ttsUrlRef.current = url
            return url
          })
          if (fallbackUrl) {
            setShowPhoto(false)
            setActiveAudio(fallbackUrl)
            setTurnState("speaking")
          } else {
            setTurnState("idle")
            processingRef.current = false
          }
        }
      } catch {
        // keep polling
      }
    }, 2000)
  }, [])

  // ── Process a VAD utterance → STT → LLM → wav2lip ────────────────────────
  const processUtterance = useCallback(async (audio: Float32Array) => {
    if (processingRef.current) return
    processingRef.current = true
    setTurnState("processing")
    setTranscribedText("")
    setError(null)

    try {
      // 1. STT
      const wav = encodeWAV(audio)
      const text = await api.sttOneshot(wav)
      if (!text.trim()) {
        setTurnState("idle")
        processingRef.current = false
        return
      }
      setTranscribedText(text)
      setDialogue((prev) => [...prev, { id: `user-${Date.now()}`, role: "user", text }])

      // 2. LLM → get response text + kick off wav2lip job
      setLatestReply("Thinking…")
      const { job_id, text: responseText, speech_text, video_url, prerendered } = await api.startConverseRespond(sessionId, text, derivedVoice)

      setDialogue((prev) => [...prev, { id: `assistant-${Date.now()}`, role: "assistant", text: responseText }])
      setLatestReply("")
      setTranscribedText("")

      if (prerendered && video_url) {
        // Pre-rendered clip — play directly, no TTS or polling needed
        setShowPhoto(false)
        setActiveVideo(video_url)
        setTurnState("speaking")
      } else {
        // Fire TTS fetch immediately — do NOT await (Bug 3 fix: no serial blocking)
        const ttsPromise = api.speakText(speech_text || responseText, derivedVoice).catch(() => null)

        if (job_id) {
          // Avatar video is primary — start rendering state and poll immediately
          setTurnState("rendering")
          // Play TTS as soon as it resolves (Bug 1 fix: user hears audio right away)
          ttsPromise.then((blob) => {
            if (!blob) return
            const url = URL.createObjectURL(blob)
            ttsUrlRef.current = url
            setShowPhoto(false)
            setActiveAudio(url)
            setTurnState("speaking")
          })
          // Start polling immediately — no await (Bug 3 fix)
          pollJob(job_id, ttsPromise)
        } else {
          // wav2lip not configured — await TTS and play directly (unchanged path)
          const blob = await ttsPromise
          if (blob) {
            const url = URL.createObjectURL(blob)
            ttsUrlRef.current = url
            setShowPhoto(false)
            setActiveAudio(url)
            setTurnState("speaking")
          } else {
            setTurnState("idle")
            processingRef.current = false
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        setError(err instanceof Error ? err.message : "Voice pipeline error")
      }
      setTurnState("idle")
      processingRef.current = false
    }
  }, [sessionId, derivedVoice, pollJob])

  // ── VAD callbacks ─────────────────────────────────────────────────────────
  const onSpeechEnd = useCallback((audio: Float32Array) => {
    if (processingRef.current) return
    if (turnStateRef.current !== "idle") return  // don't process if not idle
    void processUtterance(audio)
  }, [processUtterance])

  const onSpeechStart = useCallback(() => {
    if (!processingRef.current) setTurnState("recording")
  }, [])

  useVAD({
    onSpeechEnd,
    onSpeechStart,
    // VAD disabled — PTT is the active input mode
    enabled: false,
  })

  // ── Push-to-talk ──────────────────────────────────────────────────────────
  const onPttError = useCallback((msg: string) => setError(msg), [])
  const { startRecording, stopRecording, isRecording: pttRecording } = usePushToTalk({
    onError: onPttError,
  })

  const isPttActive = pttSupported

  async function handlePttStart() {
    if (!openingDone) return
    // Allow interrupting the interviewer — stop any playing audio/video
    if (turnState === "speaking") {
      if (audioRef.current) { audioRef.current.pause(); audioRef.current.src = "" }
      if (videoRef.current) { videoRef.current.pause(); videoRef.current.src = "" }
      setActiveAudio(null)
      setActiveVideo(null)
      setShowPhoto(true)
      processingRef.current = false
    } else if (turnState !== "idle") {
      return // don't interrupt processing/rendering
    }
    await startRecording()
    setTurnState("recording")
  }

  async function handlePttStop() {
    if (!pttRecording) return
    const blob = await stopRecording()
    if (!blob || processingRef.current) return
    await submitPttBlob(blob)
  }

  // Play a random pre-rendered thinking clip immediately while LLM+TTS processes.
  // This bridges the ~2-3s latency gap and keeps the avatar visually active.
  function playThinkingFiller() {
    const clips = thinkingClipsRef.current
    if (!clips.length) return
    const url = clips[Math.floor(Math.random() * clips.length)]
    setShowPhoto(false)
    setActiveVideo(url)
    setTurnState("speaking")
  }

  async function submitPttBlob(blob: Blob) {
    if (processingRef.current) return
    processingRef.current = true
    setTranscribedText("")
    setError(null)

    // Play filler immediately — avatar reacts before LLM responds
    playThinkingFiller()
    setTurnState("processing")

    try {
      const text = await api.sttOneshot(blob)
      if (!text.trim()) {
        setTurnState("idle")
        processingRef.current = false
        return
      }
      setTranscribedText(text)
      setDialogue((prev) => [...prev, { id: `user-${Date.now()}`, role: "user", text }])

      // LLM → get response text + kick off wav2lip job
      setLatestReply("Thinking…")
      const { job_id, text: responseText, speech_text, video_url, prerendered } = await api.startConverseRespond(sessionId, text, derivedVoice)

      setDialogue((prev) => [...prev, { id: `assistant-${Date.now()}`, role: "assistant", text: responseText }])
      setLatestReply("")
      setTranscribedText("")

      if (prerendered && video_url) {
        setShowPhoto(false)
        setActiveVideo(video_url)
        setTurnState("speaking")
      } else {
        const ttsPromise = api.speakText(speech_text || responseText, derivedVoice).catch(() => null)

        if (job_id) {
          setTurnState("rendering")
          ttsPromise.then((ttsBlob) => {
            if (!ttsBlob) return
            const url = URL.createObjectURL(ttsBlob)
            ttsUrlRef.current = url
            setShowPhoto(false)
            setActiveAudio(url)
            setTurnState("speaking")
          })
          pollJob(job_id, ttsPromise)
        } else {
          const ttsBlob = await ttsPromise
          if (ttsBlob) {
            const url = URL.createObjectURL(ttsBlob)
            ttsUrlRef.current = url
            setShowPhoto(false)
            setActiveAudio(url)
            setTurnState("speaking")
          } else {
            setTurnState("idle")
            processingRef.current = false
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        setError(err instanceof Error ? err.message : "Voice pipeline error")
      }
      setTurnState("idle")
      processingRef.current = false
    }
  }

  // ── Session load + opening sequence ──────────────────────────────────────
  // Both smalltalk and intro decisions are made synchronously in one effect so
  // there is no race between turnStateRef and the React re-render cycle.
  useEffect(() => {
    Promise.all([
      api.getSession(sessionId),
      api.getSmallTalkClips().catch(() => ({ clips: [] as string[] })),
      api.getThinkingClips().catch(() => ({ clips: [] as string[] })),
    ]).then(([s, { clips }, { clips: thinkingClips }]) => {
      thinkingClipsRef.current = thinkingClips
      setSession(s)
      const nav = location.state as { starterCode?: string; problemStatement?: string } | null
      if (s.problem_statement) {
        setProblemStatement(s.problem_statement)
        setProblemReady(true)
      } else if (nav?.problemStatement) {
        setProblemStatement(nav.problemStatement)
        setProblemReady(true)
      }
      if (s.starter_code) setCode(s.starter_code)
      else if (nav?.starterCode) setCode(nav.starterCode)
      setDialogue(buildDialogue(s.messages))

      if (hasPlayedOpeningRef.current) return
      hasPlayedOpeningRef.current = true

      const playIntro = async () => {
        try {
          const { video_url } = await api.getIntroClip()
          if (video_url) {
            setActiveVideo(video_url)
            setShowPhoto(false)
            setTurnState("speaking")
            // openingDone is set by handleVideoEnded when the intro finishes
          } else {
            await playAudioOpening(s.id)
          }
        } catch {
          await playAudioOpening(s.id)
        }
      }

      if (clips.length > 0) {
        // Play a random smalltalk clip first, then queue the intro after it ends.
        const randomClip = clips[Math.floor(Math.random() * clips.length)]
        setShowPhoto(false)
        setActiveVideo(randomClip)
        setTurnState("speaking")
        pendingIntroRef.current = () => void playIntro()
      } else {
        void playIntro()
      }
    })
  }, [sessionId, location.state]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Poll for problem readiness (background LLM processing) ───────────────
  useEffect(() => {
    if (problemReady) return  // already ready
    let cancelled = false
    const startTime = Date.now()
    const poll = async () => {
      if (Date.now() - startTime > 120_000) {
        setProblemStatement("⚠️ Problem generation timed out. Ask your interviewer to describe the problem.")
        setProblemReady(true)
        return
      }
      try {
        const status = await api.getProblemStatus(sessionId)
        if (cancelled) return
        if (status.problem_ready && status.problem_statement && status.starter_code) {
          setProblemStatement(status.problem_statement)
          setCode(status.starter_code)
          setProblemReady(true)
        } else {
          setTimeout(poll, 3000)  // retry every 3s
        }
      } catch {
        if (!cancelled) setTimeout(poll, 5000)
      }
    }
    void poll()
    return () => { cancelled = true }
  }, [sessionId, problemReady])

  // ── Cleanup ───────────────────────────────────────────────────────────────
  useEffect(() => () => {
    if (introPollerRef.current) clearInterval(introPollerRef.current)
    if (jobPollerRef.current) clearInterval(jobPollerRef.current)
  }, [])

  // ── Auto-scroll ───────────────────────────────────────────────────────────
  useEffect(() => {
    dialogueRef.current && (dialogueRef.current.scrollTop = dialogueRef.current.scrollHeight)
  }, [dialogue, latestReply])

  // ── Panel resize ──────────────────────────────────────────────────────────
  useEffect(() => {
    const mm = (e: MouseEvent) => { if (!resizingPanelsRef.current || !editorLayoutRef.current) return; const r = editorLayoutRef.current.getBoundingClientRect(); if (r.width > 0) setLeftPaneWidth(Math.max(30, Math.min(55, ((e.clientX - r.left) / r.width) * 100))) }
    const mu = () => { resizingPanelsRef.current = false }
    window.addEventListener("mousemove", mm); window.addEventListener("mouseup", mu)
    return () => { window.removeEventListener("mousemove", mm); window.removeEventListener("mouseup", mu) }
  }, [])

  // ── Code execution ────────────────────────────────────────────────────────
  async function handleRunCode() {
    if (!code.trim()) return; setRunning(true); setTerminalTab("console")
    try { const r = await api.runCode(code); setRunResult(r); api.shareCode(sessionId, code, r, undefined).catch(() => {}) }
    catch (e) { setRunResult({ stdout: "", stderr: e instanceof Error ? e.message : "Error", exit_code: -1, runtime_ms: 0, timed_out: false }) }
    finally { setRunning(false) }
  }
  async function handleRunTests() {
    if (!code.trim() || !session?.test_cases) return; setRunning(true); setTerminalTab("tests")
    try { const r = await api.runTests(code, sessionId); setTestResult(r); api.shareCode(sessionId, code, undefined, r).catch(() => {}) }
    catch (e) { console.error(e) } finally { setRunning(false) }
  }
  function handleEditorKeyDown(e: React.KeyboardEvent) {
    if (!(e.metaKey || e.ctrlKey) || e.key !== "Enter") return; e.preventDefault()
    if (e.shiftKey) void handleRunTests(); else void handleRunCode()
  }

  // ── Text-only fallback (typing) ───────────────────────────────────────────
  const [typedInput, setTypedInput] = useState("")
  async function handleTextSend() {
    const text = typedInput.trim(); if (!text) return
    setTypedInput("")
    setDialogue((prev) => [...prev, { id: `user-${Date.now()}`, role: "user", text }])
    setLatestReply("Thinking…"); setError(null)
    try {
      let acc = ""
      for await (const chunk of streamMessage(sessionId, text)) { acc += chunk; setLatestReply(acc) }
      setDialogue((prev) => [...prev, { id: `assistant-${Date.now()}`, role: "assistant", text: acc }])
      setLatestReply("")
    } catch (e) { setLatestReply(""); setError(e instanceof Error ? e.message : "Error") }
  }

  // ── Finish ────────────────────────────────────────────────────────────────
  async function handleFinishConfirmed() {
    setShowClosingPrompt(false); setFinishing(true)
    try { await api.finishSession(sessionId); navigate(`/session/${sessionId}/scorecard`) }
    catch (e) { setError(e instanceof Error ? e.message : "Failed to generate scorecard"); setFinishing(false) }
  }

  const streamingReply = useMemo(() => latestReply === "Thinking…" ? "" : latestReply, [latestReply])

  // ═══════════════════════════════════════════════════════════════════════════
  // RENDER
  // ═══════════════════════════════════════════════════════════════════════════

  return (
    <div className="h-screen overflow-hidden flex flex-col bg-background">
      {/* ── Header ──────────────────────────────────────────────────── */}
      <header className="flex justify-between items-center w-full px-6 py-3 border-b border-border bg-background shrink-0 z-50">
        <Link to="/" className="flex items-center gap-2 hover:opacity-90 transition-opacity">
          <img src="/logo.jpg" alt="grillme" className="h-9 w-9 rounded-full" />
          <span className="text-xl font-black tracking-tighter uppercase font-wordmark">
            <span className="text-on-surface">grill</span><span className="text-primary">me</span>
          </span>
        </Link>
        <div className="flex items-center gap-4 ml-auto">
          <div className="flex items-center gap-2 bg-surface-container-low px-3 py-1.5 rounded-xl border border-outline-variant/20">
            <span className="material-symbols-outlined text-tertiary text-lg" style={{ fontVariationSettings: "'FILL' 1" }}>timer</span>
            <span className="font-mono text-sm font-bold tracking-tight text-on-surface">{timer}</span>
          </div>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <Sidebar activePage="home" />

        <div ref={editorLayoutRef} className="flex flex-1 overflow-hidden">
          {/* ── Left pane: problem + dialogue ──────────────────────── */}
          <div style={{ width: `${leftPaneWidth}%` }} className="border-r border-border bg-surface-container-low flex flex-col overflow-hidden">
            {/* Problem header */}
            <div className="border-b border-border bg-surface-container-low shrink-0">
              <div className="px-4 py-2 flex items-center justify-between">
                <button onClick={() => setProblemCollapsed((c) => !c)} className="flex items-center gap-2 text-left">
                  <span className="material-symbols-outlined text-primary text-base" style={{ fontVariationSettings: "'FILL' 1" }}>{problemCollapsed ? "chevron_right" : "expand_more"}</span>
                  <span className="text-xs font-bold text-on-surface uppercase tracking-widest">Coding Problem</span>
                </button>
                {session?.difficulty && <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-primary/10 text-primary border border-primary/30">{session.difficulty}</span>}
              </div>
              {!problemCollapsed && (
                <div className="px-4 pb-3 max-h-52 overflow-y-auto no-scrollbar">
                  {problemReady ? (
                    <div className="text-xs text-on-surface leading-relaxed prose prose-invert prose-xs max-w-none [&_pre]:bg-surface-container [&_pre]:rounded [&_pre]:p-2 [&_pre]:overflow-x-auto [&_code]:text-[11px] [&_p]:mb-1 [&_ul]:mt-1 [&_ol]:mt-1">
                      <ReactMarkdown>{problemStatement}</ReactMarkdown>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2 text-xs text-on-surface-variant/60 py-1">
                      <span className="material-symbols-outlined text-sm animate-spin">progress_activity</span>
                      Preparing problem… (ready before coding phase)
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="px-4 py-2 border-b border-border shrink-0">
              <span className="text-[11px] font-bold text-on-surface uppercase tracking-widest">Interview Dialogue</span>
            </div>

            {/* Dialogue */}
            <div ref={dialogueRef} className="flex-1 overflow-y-auto no-scrollbar p-3 space-y-2">
              {dialogue.length === 0 && !streamingReply ? (
                <p className="text-xs italic text-on-surface-variant/60">Interview conversation will appear here.</p>
              ) : (
                <>
                  {dialogue.map((turn) => (
                    <div key={turn.id} className={cn("max-w-[92%] rounded-lg px-2.5 py-2 text-xs leading-relaxed", turn.role === "assistant" ? "mr-auto bg-surface-container text-on-surface border border-outline-variant/20" : "ml-auto bg-primary/10 border border-primary/30 text-on-surface whitespace-pre-wrap")}>
                      <span className={cn("mb-1 block text-[10px] font-bold uppercase tracking-widest", turn.role === "assistant" ? "text-primary/80" : "text-blue-300/90")}>
                        {turn.role === "assistant" ? "Interviewer" : "You"}
                      </span>
                      {turn.role === "assistant" ? (
                        <div className="prose prose-invert prose-xs max-w-none [&_p]:mb-0.5 [&_p]:leading-relaxed [&_code]:text-[11px] [&_pre]:bg-black/30 [&_pre]:rounded [&_pre]:p-1.5 [&_pre]:overflow-x-auto">
                          <ReactMarkdown>{turn.text}</ReactMarkdown>
                        </div>
                      ) : turn.text}
                    </div>
                  ))}
                  {(isProcessing || isSpeaking || isRendering || streamingReply) && (
                    <div className="max-w-[92%] mr-auto rounded-lg px-2.5 py-2 text-xs leading-relaxed bg-surface-container text-on-surface border border-outline-variant/20">
                      <span className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-primary/80">Interviewer</span>
                      <div className="prose prose-invert prose-xs max-w-none [&_p]:mb-0.5 [&_code]:text-[11px]">
                        <ReactMarkdown>{latestReply}</ReactMarkdown>
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>

            {error && (
              <div className="mx-4 mb-3 flex items-center gap-2 text-error text-xs px-3 py-2 bg-error-container/10 rounded-xl border border-error/20 shrink-0">
                <span className="material-symbols-outlined text-sm">error</span>{error}
              </div>
            )}

            {/* ── Bottom bar ──── */}
            <div className="px-4 py-3 border-t border-border shrink-0 flex items-center gap-3">
              {/* Mic permission denied banner */}
              {micError && (
                <div className="absolute bottom-28 left-4 right-4 flex items-center gap-2 text-red-400 text-xs px-3 py-2 bg-red-500/10 rounded-xl border border-red-500/20">
                  <span className="material-symbols-outlined text-sm">mic_off</span>
                  {micError}
                  <button onClick={() => setMicError(null)} className="ml-auto text-red-400/60 hover:text-red-400">
                    <span className="material-symbols-outlined text-sm">close</span>
                  </button>
                </div>
              )}

              {/* Single mic button — hold to speak (PTT) */}
              <div className="relative shrink-0">
                <button
                  type="button"
                  onMouseDown={isPttActive ? () => void handlePttStart() : undefined}
                  onMouseUp={isPttActive ? () => void handlePttStop() : undefined}
                  onMouseLeave={isPttActive ? () => void handlePttStop() : undefined}
                  onTouchStart={() => void handlePttStart()}
                  onTouchEnd={() => void handlePttStop()}
                  className={cn(
                    "w-9 h-9 rounded-full flex items-center justify-center transition-all duration-200 border select-none",
                    pttRecording
                      ? "bg-red-500 border-red-400 shadow-lg shadow-red-500/30 scale-105"
                      : (isProcessing || isRendering) || !openingDone
                      ? "bg-surface-container-highest border-outline-variant/30 text-outline opacity-40 cursor-not-allowed"
                      : "bg-blue-500/20 border-blue-400/40 text-blue-400 cursor-pointer",
                  )}
                >
                  <span className="material-symbols-outlined text-base" style={{ fontVariationSettings: "'FILL' 1" }}>
                    {pttRecording ? "graphic_eq" : "mic"}
                  </span>
                </button>
                {/* PTT badge */}
                <span className="absolute -bottom-1 -right-1 text-[8px] font-bold uppercase px-1 rounded-full border bg-background border-outline-variant/40 text-outline leading-tight select-none">hold</span>
              </div>

              {pttRecording ? (
                <div className="flex items-center gap-2 min-w-0 shrink-0">
                  {[0, 80, 160, 240].map((d) => (
                    <div key={d} className="w-0.5 rounded-full bar-wave bg-red-400" style={{ animationDelay: `${d}ms`, height: "10px" }} />
                  ))}
                  <span className="text-xs text-red-400 font-medium">Recording…</span>
                </div>
              ) : isProcessing && transcribedText ? (
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-blue-300 italic leading-relaxed truncate">"{transcribedText}"</p>
                  <p className="text-[10px] text-on-surface-variant/60 mt-0.5">Waiting for response…</p>
                </div>
              ) : isProcessing ? (
                <div className="flex items-center gap-2 shrink-0">
                  <span className="material-symbols-outlined text-sm animate-spin text-on-surface-variant/60">progress_activity</span>
                  <span className="text-xs text-on-surface-variant/60">Transcribing…</span>
                </div>
              ) : isRendering ? (
                <div className="flex items-center gap-2 shrink-0">
                  <span className="material-symbols-outlined text-sm animate-spin text-primary/60">progress_activity</span>
                  <span className="text-xs text-primary/60">Rendering video…</span>
                </div>
              ) : isSpeaking ? (
                <div className="flex items-center gap-2 shrink-0">
                  {[0, 110, 220, 330, 440].map((d) => (
                    <div key={d} className="w-0.5 rounded-full bar-wave bg-primary" style={{ animationDelay: `${d}ms`, height: "8px" }} />
                  ))}
                  <span className="text-xs text-primary/80 font-medium">Speaking…</span>
                </div>
              ) : null}

              <div className="flex-1 flex items-center gap-2 min-w-0">
                <input
                  type="text"
                  value={typedInput}
                  onChange={(e) => setTypedInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void handleTextSend() } }}
                  placeholder={
                    isRendering ? "Preparing response…"
                    : isSpeaking ? "Interviewer is speaking…"
                    : "Hold mic to speak, or type here"
                  }
                  disabled={isSpeaking || isProcessing || isRendering}
                  className="flex-1 bg-transparent text-xs text-on-surface placeholder:text-outline/40 outline-none disabled:opacity-40"
                />
                {typedInput.trim() && (
                  <button onClick={() => void handleTextSend()} className="text-primary text-xs font-semibold hover:text-primary/80">Send</button>
                )}
              </div>
            </div>
          </div>

          {/* ── Resize handle ─────────────────────────────────────── */}
          <div className="w-1.5 bg-border/70 hover:bg-primary/60 cursor-col-resize shrink-0 transition-colors" onMouseDown={() => { resizingPanelsRef.current = true }} />

          {/* ── Right pane: editor + terminal ──────────────────────── */}
          <div className="flex-1 flex flex-col bg-surface-container-lowest overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2 bg-surface-container-low border-b border-border shrink-0">
              <div className="flex items-center gap-2 px-3 py-1 bg-surface-container-highest rounded-lg text-xs font-semibold text-on-surface border border-outline-variant/20">
                <span className="w-2 h-2 rounded-full bg-blue-400" /> Python 3.13
              </div>
              <div className="flex gap-2">
                <button onClick={handleRunCode} disabled={running || !code.trim()} className="px-3 py-1 text-xs font-semibold rounded-lg bg-surface-container-highest text-on-surface-variant hover:bg-surface-bright transition-colors disabled:opacity-40">Run Code</button>
                <button onClick={handleRunTests} disabled={running || !code.trim() || !session?.test_cases} className="px-3 py-1 text-xs font-semibold rounded-lg bg-primary/20 text-primary hover:bg-primary/30 transition-colors disabled:opacity-40">Run Tests</button>
                <button className="px-3 py-1 text-xs font-bold rounded-lg bg-surface-container-highest text-on-surface hover:bg-surface-bright transition-colors active:scale-[0.97] disabled:opacity-40" onClick={() => setShowClosingPrompt(true)} disabled={finishing}>
                  {finishing ? <span className="material-symbols-outlined text-sm animate-spin">progress_activity</span> : "Finish & Score"}
                </button>
              </div>
            </div>

            <div className="h-[70%] border-b border-border">
              <div onKeyDown={handleEditorKeyDown} className="h-full">
                {problemReady ? (
                  <Editor height="100%" defaultLanguage="python" theme="vs-dark" value={code} onChange={(v) => setCode(v ?? "")} options={{ fontSize: 13, minimap: { enabled: false }, lineNumbers: "on", scrollBeyondLastLine: false, automaticLayout: true }} />
                ) : (
                  <div className="h-full flex flex-col items-center justify-center gap-3 bg-[#1e1e1e]">
                    <span className="material-symbols-outlined text-3xl text-outline/40 animate-spin">progress_activity</span>
                    <p className="text-xs text-outline/50">Preparing your coding problem…</p>
                    <p className="text-[10px] text-outline/30">Ready before the coding phase starts</p>
                  </div>
                )}
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

      {/* ── Avatar PIP (wav2lip video or static photo) ────────────────── */}
      <div
        className="fixed z-50 w-32 rounded-2xl overflow-hidden glass-panel shadow-2xl select-none touch-none"
        style={{ left: pip.pos.x, top: pip.pos.y }}
      >
        {/* Title bar / drag handle */}
        <div
          className="flex items-center justify-between px-3 py-2 bg-surface-container/90 cursor-grab active:cursor-grabbing border-b border-white/5"
          onMouseDown={pip.onMouseDown}
          onTouchStart={pip.onTouchStart}
        >
          <div className="flex items-center gap-2 min-w-0">
            <div className={cn(
              "w-1.5 h-1.5 shrink-0 rounded-full transition-colors duration-300",
              isSpeaking ? "bg-primary animate-pulse"
                : isRecording ? "bg-red-400 animate-pulse"
                : isRendering ? "bg-yellow-400 animate-pulse"
                : "bg-outline/40",
            )} />
            <span className="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant truncate">{personaName}</span>
          </div>
          <div className="flex items-end gap-px h-4 shrink-0 ml-2">
            {isSpeaking && [0, 110, 220, 330, 440].map((d) => (
              <div key={d} className="w-0.5 rounded-full bar-wave bg-primary" style={{ animationDelay: `${d}ms`, height: "8px" }} />
            ))}
            {isRecording && [0, 160, 320].map((d) => (
              <div key={d} className="w-0.5 rounded-full bar-wave bg-red-400" style={{ animationDelay: `${d}ms`, height: "8px" }} />
            ))}
          </div>
        </div>

        {/* Grip stripe */}
        <div
          className="flex items-center justify-center h-3 bg-surface-container-high/80 border-b border-white/5 cursor-grab"
          onMouseDown={pip.onMouseDown}
          onTouchStart={pip.onTouchStart}
        >
          <div className="w-8 h-px rounded-full bg-outline/25" />
        </div>

        {/* Portrait / video */}
        <div className="relative" style={{ aspectRatio: "3/4" }}>
          {/* Hidden audio element for TTS fallback */}
          <audio
            ref={audioRef}
            src={activeAudio ?? undefined}
            autoPlay
            onEnded={handleAudioEnded}
            style={{ display: "none" }}
          />

          <div className="w-full h-full relative overflow-hidden bg-[#1a1a1a]">
            {/* Static photo — uses same class as video for identical framing */}
            <img
              src={photoSrc}
              alt={personaName}
              className={`${AVATAR_MEDIA_CLASS} transition-opacity duration-500`}
              style={{ opacity: showPhoto && !activeVideo ? 1 : 0 }}
            />

            {/* Wav2lip video */}
            {activeVideo && (
              <video
                ref={videoRef}
                src={activeVideo}
                autoPlay
                playsInline
                onEnded={handleVideoEnded}
                onCanPlay={(e) => {
                  const vid = e.currentTarget
                  // Mute if TTS already played — prevent replaying the same audio
                  vid.muted = ttsFinishedRef.current
                  vid.volume = ttsFinishedRef.current ? 0 : 1.0
                  vid.play().catch(() => {})
                }}
                className={AVATAR_MEDIA_CLASS}
              />
            )}

            {/* Rendering overlay */}
            {isRendering && !activeVideo && (
              <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/50">
                <span className="material-symbols-outlined text-2xl text-white/80 animate-spin">progress_activity</span>
                <span className="text-[10px] text-white/70 mt-1 uppercase tracking-widest">Preparing…</span>
              </div>
            )}

            {/* Name + status bar — overlaid at bottom */}
            <div className="absolute bottom-0 inset-x-0 flex flex-col items-center gap-0.5 py-2 bg-gradient-to-t from-black/60 to-transparent">
              <span className="text-[11px] font-semibold text-white drop-shadow text-center leading-tight">{personaName}</span>
              <span
                className="text-[9px] uppercase tracking-widest font-medium transition-colors duration-300"
                style={{
                  color: isSpeaking
                    ? "rgba(224,160,100,0.95)"
                    : isRecording
                    ? "rgba(248,113,113,0.95)"
                    : isRendering
                    ? "rgba(250,204,21,0.9)"
                    : "rgba(200,200,200,0.6)",
                }}
              >
                {statusLabel}
              </span>
            </div>

            {/* Pulse glow */}
            {(isSpeaking || isRecording) && (
              <span className={cn(
                "absolute inset-0 animate-ping opacity-[0.07] pointer-events-none",
                isSpeaking ? "bg-primary" : "bg-red-400",
              )} />
            )}
          </div>
        </div>
      </div>

      {/* ── Finish modal ────────────────────────────────────────────────── */}
      {showClosingPrompt && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-xl rounded-2xl border border-outline-variant/30 bg-surface-container p-5 space-y-4">
            <h3 className="text-lg font-bold text-on-surface">Before you finish</h3>
            <p className="text-sm text-on-surface-variant leading-relaxed">Do you have any questions for the interviewer? Asking thoughtful questions about the team, role, or what they care about is part of the interview and will affect your score.</p>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setShowClosingPrompt(false)} className="px-3 py-2 text-xs font-semibold rounded-lg border border-outline-variant/30 text-on-surface-variant hover:bg-surface-container-high transition-colors">I have questions</button>
              <button type="button" onClick={handleFinishConfirmed} className="px-3 py-2 text-xs font-semibold rounded-lg shimmer-gradient text-on-primary hover:opacity-90 transition-opacity">I'm done — score me</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
