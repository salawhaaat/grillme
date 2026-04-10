import { useState, useRef, useEffect } from "react"
import { useNavigate } from "react-router-dom"
import { api, type SessionInfo, type Difficulty } from "@/lib/api/client"
import { cn } from "@/lib/utils"
import { Sidebar } from "@/components/Sidebar"
import { DIFFICULTY_PICKER_META } from "@/lib/constants/difficulty"

type Step = "paste" | "confirm"
type SourceTab = "jd" | "problem"

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

  useEffect(() => {
    function onMouseMove(e: MouseEvent) {
      if (!dragging.current) return
      setPos({ x: e.clientX - offset.current.x, y: e.clientY - offset.current.y })
    }
    function onMouseUp() {
      dragging.current = false
    }
    window.addEventListener("mousemove", onMouseMove)
    window.addEventListener("mouseup", onMouseUp)
    return () => {
      window.removeEventListener("mousemove", onMouseMove)
      window.removeEventListener("mouseup", onMouseUp)
    }
  }, [])

  return { pos, onMouseDown }
}

export default function Home() {
  const navigate = useNavigate()
  const [sourceTab, setSourceTab] = useState<SourceTab>("jd")
  const [jd, setJd] = useState("")
  const [problemUrl, setProblemUrl] = useState("")
  const [step, setStep] = useState<Step>("paste")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sessionInfo, setSessionInfo] = useState<SessionInfo | null>(null)
  const [showPrepPlan, setShowPrepPlan] = useState(true)
  const [fileDragging, setFileDragging] = useState(false)
  const [difficulty, setDifficulty] = useState<Difficulty>("medium")
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Draggable talking head — starts top-right of the right panel
  const pip = useDraggable({ x: window.innerWidth - 320, y: 80 })

  async function handleAnalyze() {
    if (!jd.trim()) return
    setLoading(true)
    setError(null)
    try {
      const info = await api.createSessionFromJD(jd, difficulty)
      setSessionInfo(info)
      setStep("confirm")
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong")
    } finally {
      setLoading(false)
    }
  }

  async function handleStartFromProblem() {
    if (!problemUrl.trim()) return
    if (!problemUrl.includes("leetcode.com/problems/")) {
      setError("URL must contain leetcode.com/problems/")
      return
    }

    setLoading(true)
    setError(null)
    try {
      const info = await api.createFromProblem(problemUrl.trim(), difficulty)
      navigate(`/session/${info.session_id}`, {
        state: { openingMessage: info.opening_message },
      })
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong")
    } finally {
      setLoading(false)
    }
  }

  function handleStart() {
    if (sessionInfo) {
      navigate(`/session/${sessionInfo.session_id}`, {
        state: { openingMessage: sessionInfo.opening_message },
      })
    }
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault()
    setFileDragging(true)
  }

  function handleDragLeave() {
    setFileDragging(false)
  }

  async function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setFileDragging(false)
    const text = e.dataTransfer.getData("text/plain")
    if (text) { setJd(text); return }
    const file = e.dataTransfer.files[0]
    if (file && file.type === "text/plain") setJd(await file.text())
  }

  async function handlePasteFromClipboard() {
    try {
      setJd(await navigator.clipboard.readText())
      textareaRef.current?.focus()
    } catch {
      textareaRef.current?.focus()
    }
  }

  return (
    <div className="h-screen overflow-hidden flex flex-col bg-background">
      {/* ── Header ── */}
      <header className="flex justify-between items-center w-full px-6 py-3 border-b border-border bg-background shrink-0 z-50">
        <div className="flex items-center gap-2">
          <img src="/logo.jpg" alt="grillme" className="h-9 w-9 rounded-full" />
          <span className="text-xl font-black tracking-tighter uppercase font-wordmark"><span className="text-on-surface">grill</span><span className="text-primary">me</span></span>
        </div>
        <div />
      </header>

      <div className="flex flex-1 overflow-hidden">
        <Sidebar activePage="home" />

        {/* ── Main workspace ── */}
        <div className="flex flex-1 overflow-hidden relative">
          {/* ── LEFT PANEL — JD input ── */}
          <div className="w-[45%] flex flex-col border-r border-border bg-surface-container-low">
            <div className="flex items-center justify-between px-4 py-2 bg-surface-container-low border-b border-border shrink-0">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-primary text-sm" style={{ fontVariationSettings: "'FILL' 1" }}>
                  description
                </span>
                <span className="text-xs font-bold text-on-surface uppercase tracking-widest font-label">
                  {sourceTab === "jd" ? "Job Description" : "Problem URL"}
                </span>
              </div>
              {sourceTab === "jd" && jd.trim() && step === "paste" && (
                <button
                  onClick={() => setJd("")}
                  className="text-[10px] text-outline hover:text-error transition-colors flex items-center gap-1"
                >
                  <span className="material-symbols-outlined text-sm">close</span>
                  clear
                </button>
              )}
            </div>

            <div className="px-4 pt-3">
              <div className="inline-flex rounded-xl border border-outline-variant/30 bg-surface-container-lowest p-1 gap-1">
                <button
                  onClick={() => {
                    setSourceTab("jd")
                    setError(null)
                  }}
                  className={cn(
                    "px-3 py-1.5 text-xs font-semibold rounded-lg border transition-colors",
                    sourceTab === "jd"
                      ? "bg-primary/20 border-primary text-primary"
                      : "border-transparent text-on-surface-variant hover:text-on-surface",
                  )}
                >
                  From JD
                </button>
                <button
                  onClick={() => {
                    setSourceTab("problem")
                    setError(null)
                    setStep("paste")
                  }}
                  className={cn(
                    "px-3 py-1.5 text-xs font-semibold rounded-lg border transition-colors",
                    sourceTab === "problem"
                      ? "bg-primary/20 border-primary text-primary"
                      : "border-transparent text-on-surface-variant hover:text-on-surface",
                  )}
                >
                  From Problem
                </button>
              </div>
            </div>

            {step === "paste" && sourceTab === "jd" && (
              <div className="flex-1 flex flex-col p-4 gap-3 overflow-hidden">
                {/* Drop zone */}
                <div
                  className={cn(
                    "flex-1 relative rounded-xl border-2 border-dashed transition-all duration-200 overflow-hidden",
                    fileDragging
                      ? "border-primary bg-primary/5 scale-[0.99]"
                      : jd
                      ? "border-outline-variant/30 bg-surface-container-lowest"
                      : "border-outline-variant/20 bg-surface-container-lowest hover:border-outline-variant/40",
                  )}
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                >
                  {!jd && !fileDragging && (
                    <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 pointer-events-none select-none">
                      <span className="material-symbols-outlined text-5xl text-outline/25" style={{ fontVariationSettings: "'FILL' 1" }}>
                        upload_file
                      </span>
                      <div className="text-center space-y-1">
                        <p className="text-sm font-semibold text-on-surface-variant">Drop a .txt file here</p>
                        <p className="text-xs text-outline">or paste / type below</p>
                      </div>
                      <div className="flex items-center gap-3">
                        <div className="h-px w-14 bg-outline-variant/30" />
                        <span className="text-[10px] text-outline uppercase tracking-widest">or</span>
                        <div className="h-px w-14 bg-outline-variant/30" />
                      </div>
                      <button
                        className="pointer-events-auto flex items-center gap-2 px-4 py-2 rounded-xl border border-outline-variant/30 text-xs font-semibold text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface transition-all"
                        onClick={handlePasteFromClipboard}
                      >
                        <span className="material-symbols-outlined text-sm">content_paste</span>
                        Paste from clipboard
                      </button>
                    </div>
                  )}

                  {fileDragging && (
                    <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 pointer-events-none">
                      <span className="material-symbols-outlined text-5xl text-primary animate-bounce">move_to_inbox</span>
                      <p className="text-sm font-bold text-primary">Drop it here</p>
                    </div>
                  )}

                  <textarea
                    ref={textareaRef}
                    className={cn(
                      "w-full h-full resize-none bg-transparent font-mono text-xs text-on-surface placeholder:text-outline/30 focus:outline-none p-4 transition-opacity",
                      !jd && !fileDragging ? "opacity-0 pointer-events-none" : "opacity-100",
                    )}
                    placeholder="Paste job description here..."
                    value={jd}
                    onChange={(e) => setJd(e.target.value)}
                  />
                </div>

                <div className="flex flex-col gap-2 shrink-0">
                  {!jd && (
                    <button
                      onClick={() => { setJd(" "); setTimeout(() => { setJd(""); textareaRef.current?.focus() }, 0) }}
                      className="w-full py-2.5 text-xs font-semibold rounded-xl border border-outline-variant/30 text-on-surface-variant hover:bg-surface-container-high transition-colors flex items-center justify-center gap-2"
                    >
                      <span className="material-symbols-outlined text-sm">edit</span>
                      Type manually
                    </button>
                  )}

                  {/* Difficulty selector */}
                  <div className="space-y-1.5">
                    <p className="text-[10px] font-bold text-outline uppercase tracking-wider px-0.5">
                      Difficulty
                    </p>
                    <div className="grid grid-cols-3 gap-2">
                      {(Object.entries(DIFFICULTY_PICKER_META) as [Difficulty, typeof DIFFICULTY_PICKER_META[Difficulty]][]).map(([key, meta]) => (
                        <button
                          key={key}
                          onClick={() => setDifficulty(key)}
                          className={cn(
                            "flex flex-col items-center gap-1 py-2.5 rounded-xl border text-xs font-semibold transition-all",
                            difficulty === key ? meta.active : meta.color,
                          )}
                        >
                          <span
                            className="material-symbols-outlined text-base"
                            style={{ fontVariationSettings: "'FILL' 1" }}
                          >
                            {meta.icon}
                          </span>
                          <span className="font-bold">{meta.label}</span>
                          <span className="text-[10px] opacity-70">{meta.desc}</span>
                        </button>
                      ))}
                    </div>
                  </div>

                  {error && (
                    <p className="text-error text-xs flex items-center gap-1.5 px-1">
                      <span className="material-symbols-outlined text-sm">error</span>
                      {error}
                    </p>
                  )}
                  <button
                    className="w-full py-2.5 text-sm font-bold rounded-xl shimmer-gradient text-on-primary hover:opacity-90 transition-opacity active:scale-[0.98] disabled:opacity-30 disabled:pointer-events-none flex items-center justify-center gap-2"
                    onClick={handleAnalyze}
                    disabled={loading || !jd.trim()}
                  >
                    {loading ? (
                      <>
                        <span className="material-symbols-outlined text-sm animate-spin">progress_activity</span>
                        Building interviewer…
                      </>
                    ) : (
                      <>
                        <span className="material-symbols-outlined text-sm">psychology</span>
                        Analyze & Build Interviewer
                      </>
                    )}
                  </button>
                </div>
              </div>
            )}

            {step === "paste" && sourceTab === "problem" && (
              <div className="flex-1 flex flex-col p-4 gap-3 overflow-hidden">
                <div className="bg-surface-container-lowest rounded-xl border border-outline-variant/20 p-4 space-y-3">
                  <label className="text-[10px] font-bold text-outline uppercase tracking-wider">
                    LeetCode URL
                  </label>
                  <input
                    type="text"
                    value={problemUrl}
                    onChange={(e) => setProblemUrl(e.target.value)}
                    placeholder="https://leetcode.com/problems/two-sum/"
                    className="w-full bg-transparent border border-outline-variant/30 rounded-xl px-3 py-2 text-sm text-on-surface placeholder:text-outline focus:outline-none focus:border-primary/50"
                  />
                </div>

                <div className="space-y-1.5">
                  <p className="text-[10px] font-bold text-outline uppercase tracking-wider px-0.5">
                    Difficulty
                  </p>
                  <div className="grid grid-cols-3 gap-2">
                    {(Object.entries(DIFFICULTY_PICKER_META) as [Difficulty, typeof DIFFICULTY_PICKER_META[Difficulty]][]).map(([key, meta]) => (
                      <button
                        key={key}
                        onClick={() => setDifficulty(key)}
                        className={cn(
                          "flex flex-col items-center gap-1 py-2.5 rounded-xl border text-xs font-semibold transition-all",
                          difficulty === key ? meta.active : meta.color,
                        )}
                      >
                        <span
                          className="material-symbols-outlined text-base"
                          style={{ fontVariationSettings: "'FILL' 1" }}
                        >
                          {meta.icon}
                        </span>
                        <span className="font-bold">{meta.label}</span>
                        <span className="text-[10px] opacity-70">{meta.desc}</span>
                      </button>
                    ))}
                  </div>
                </div>

                {error && (
                  <p className="text-error text-xs flex items-center gap-1.5 px-1">
                    <span className="material-symbols-outlined text-sm">error</span>
                    {error}
                  </p>
                )}
                <button
                  className="w-full py-2.5 text-sm font-bold rounded-xl shimmer-gradient text-on-primary hover:opacity-90 transition-opacity active:scale-[0.98] disabled:opacity-30 disabled:pointer-events-none flex items-center justify-center gap-2"
                  onClick={handleStartFromProblem}
                  disabled={loading || !problemUrl.trim()}
                >
                  {loading ? (
                    <>
                      <span className="material-symbols-outlined text-sm animate-spin">progress_activity</span>
                      Starting session…
                    </>
                  ) : (
                    <>
                      <span className="material-symbols-outlined text-sm">code</span>
                      Start Coding Interview
                    </>
                  )}
                </button>
              </div>
            )}

            {step === "confirm" && sourceTab === "jd" && sessionInfo && (
              <div className="flex-1 flex flex-col p-4 gap-4 overflow-y-auto no-scrollbar">
                <div className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-green-400 text-lg" style={{ fontVariationSettings: "'FILL' 1" }}>
                    check_circle
                  </span>
                  <h2 className="font-headline font-bold text-on-surface tracking-tight">Interviewer ready</h2>
                </div>
                <div className="flex flex-wrap gap-2">
                  {sessionInfo.company && (
                    <span className="px-3 py-1 text-xs font-bold uppercase tracking-wider rounded-full bg-primary/10 text-primary border border-primary/20">
                      {sessionInfo.company}
                    </span>
                  )}
                  {sessionInfo.role && (
                    <span className="px-3 py-1 text-xs font-bold uppercase tracking-wider rounded-full bg-secondary-container/30 text-secondary border border-secondary/20">
                      {sessionInfo.role}
                    </span>
                  )}
                  {sessionInfo.level && (
                    <span className="px-3 py-1 text-xs font-bold uppercase tracking-wider rounded-full bg-surface-container-highest text-on-surface-variant border border-outline-variant/30">
                      {sessionInfo.level}
                    </span>
                  )}
                </div>
                <div className="bg-surface-container-lowest rounded-xl p-4 border border-outline-variant/20 flex-1">
                  <p className="text-[10px] font-bold text-outline uppercase tracking-wider mb-2 flex items-center gap-1.5">
                    <span className="material-symbols-outlined text-sm">interpreter_mode</span>
                    Opening message
                  </p>
                  <p className="text-sm text-on-surface leading-relaxed">"{sessionInfo.opening_message}"</p>
                </div>
                {sessionInfo.prep_plan && (
                  <div className="bg-surface-container-lowest rounded-xl border border-outline-variant/20">
                    <button
                      type="button"
                      onClick={() => setShowPrepPlan((v) => !v)}
                      className="w-full flex items-center justify-between px-4 py-3 text-left"
                    >
                      <p className="text-sm font-bold text-on-surface">Your Prep Plan</p>
                      <span className="material-symbols-outlined text-sm text-outline">
                        {showPrepPlan ? "expand_less" : "expand_more"}
                      </span>
                    </button>
                    {showPrepPlan && (
                      <ol className="px-8 pb-4 list-decimal space-y-1 text-sm text-on-surface-variant">
                        {sessionInfo.prep_plan
                          .split("\n")
                          .map((line) => line.trim())
                          .filter(Boolean)
                          .map((line, idx) => (
                            <li key={idx}>{line}</li>
                          ))}
                      </ol>
                    )}
                  </div>
                )}
                <div className="flex gap-3 shrink-0">
                  <button
                    className="flex-1 py-2.5 text-sm font-semibold rounded-xl border border-outline-variant/30 text-on-surface-variant bg-surface-container-lowest hover:bg-surface-container-high transition-colors"
                    onClick={() => setStep("paste")}
                  >
                    Back
                  </button>
                  <button
                    className="flex-1 py-2.5 text-sm font-bold rounded-xl shimmer-gradient text-on-primary hover:opacity-90 transition-opacity active:scale-[0.98] flex items-center justify-center gap-2"
                    onClick={handleStart}
                  >
                    <span className="material-symbols-outlined text-sm">play_arrow</span>
                    Start Interview
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* ── RIGHT PANEL — editor + terminal ── */}
          <div className="flex-1 flex flex-col bg-surface-container-lowest overflow-hidden">
            {/* Editor header */}
            <div className="flex items-center justify-between px-4 py-2 bg-surface-container-low border-b border-border shrink-0">
              <div className="flex items-center gap-2 px-3 py-1 bg-surface-container-highest rounded-lg text-xs font-semibold text-on-surface border border-outline-variant/20">
                <span className="w-2.5 h-2.5 bg-blue-400 rounded-full" />
                Python 3.11
                <span className="material-symbols-outlined text-sm text-outline">expand_more</span>
              </div>
              <div className="flex gap-2">
                <button className="p-1.5 text-outline hover:text-on-surface transition-colors">
                  <span className="material-symbols-outlined text-lg">format_align_left</span>
                </button>
                <button className="px-3 py-1 text-xs font-semibold rounded-lg bg-surface-container-highest text-on-surface-variant hover:bg-surface-bright transition-colors">
                  Run Code
                </button>
              </div>
            </div>

            {/* Code body */}
            <div className="flex-1 flex font-mono text-[13px] overflow-hidden">
              <div className="w-10 bg-surface-container-lowest text-outline/30 flex flex-col items-end pr-3 py-4 select-none text-xs gap-[1.5rem] shrink-0">
                {Array.from({ length: 8 }, (_, i) => <span key={i}>{i + 1}</span>)}
              </div>
              <div className="flex-1 p-4 overflow-y-auto no-scrollbar text-sm leading-[1.75rem]">
                <div className="text-outline/30 italic text-xs mb-3">
                  {/* placeholder */}# Your solution will appear here during the interview
                </div>
                <div>
                  <span className="text-primary/50">class</span>
                  <span className="text-on-surface/30"> Solution:</span>
                </div>
                <div className="pl-8">
                  <span className="text-primary/50">def</span>
                  <span className="text-on-surface/30"> solve(self) -&gt; None:</span>
                </div>
                <div className="pl-16 text-outline/25"># start your session to begin</div>
                <span className="inline-block w-1.5 h-5 bg-primary/20 animate-pulse rounded-sm ml-16 align-middle" />
              </div>
            </div>

            {/* Terminal */}
            <div className="h-[22%] border-t border-border flex flex-col shrink-0">
              <div className="flex items-center justify-between px-4 py-1.5 border-b border-border bg-surface-container-low shrink-0">
                <div className="flex gap-4">
                  <button className="text-[10px] font-bold uppercase tracking-widest text-primary border-b border-primary">Console</button>
                  <button className="text-[10px] font-bold uppercase tracking-widest text-outline hover:text-on-surface">Test Results</button>
                </div>
                <span className="material-symbols-outlined text-sm text-outline hover:text-on-surface cursor-pointer">close_fullscreen</span>
              </div>
              <div className="flex-1 p-4 font-mono text-xs overflow-y-auto no-scrollbar text-outline/50 space-y-1">
                <div className="flex gap-2">
                  <span className="text-secondary/40">$</span>
                  <span>python solution.py --test</span>
                </div>
                <div className="text-outline/25 italic">&gt; Waiting for session to start…</div>
              </div>
            </div>
          </div>

          {/* ── Draggable Talking Head (fixed to viewport) ── */}
          <div
            className="fixed z-50 w-72 rounded-2xl overflow-hidden glass-panel shadow-2xl select-none"
            style={{ left: pip.pos.x, top: pip.pos.y }}
          >
            {/* Drag handle */}
            <div
              className="flex items-center justify-between px-3 py-2 bg-surface-container/90 cursor-grab active:cursor-grabbing border-b border-white/5"
              onMouseDown={pip.onMouseDown}
            >
              <div className="flex items-center gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-outline/40 animate-pulse" />
                <span className="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">
                  AI Interviewer
                </span>
              </div>
              <span className="material-symbols-outlined text-sm text-outline/50">drag_indicator</span>
            </div>

            {/* Avatar */}
            <div className="relative bg-surface-container-low" style={{ aspectRatio: "16/9" }}>
              <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-surface-container to-surface-container-highest">
                <span
                  className="material-symbols-outlined text-7xl text-outline/20"
                  style={{ fontVariationSettings: "'FILL' 1" }}
                >
                  face
                </span>
              </div>
              <div className="absolute top-2 left-2 flex items-center gap-1.5 bg-black/50 backdrop-blur-md px-2 py-1 rounded-lg">
                <div className="w-1.5 h-1.5 rounded-full bg-outline/50 animate-pulse" />
                <span className="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Waiting</span>
              </div>
            </div>

            {/* Caption */}
            <div className="p-3 bg-surface-container/80 backdrop-blur-md">
              <div className="bg-black/20 px-3 py-2 rounded-xl border border-white/5">
                <p className="text-xs text-outline leading-relaxed italic">
                  Paste a JD to build your interviewer persona…
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
