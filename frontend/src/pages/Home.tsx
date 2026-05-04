import { useEffect, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import { api, type Difficulty, type SessionSource } from "@/lib/api/client"
import { cn } from "@/lib/utils"
import { Sidebar } from "@/components/Sidebar"
import { DIFFICULTY_PICKER_META } from "@/lib/constants/difficulty"
import * as pdfjsLib from "pdfjs-dist"
import pdfjsWorkerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url"

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfjsWorkerUrl

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

  const stopDragging = () => {
    dragging.current = false
  }

  return { pos, onMouseDown, onTouchStart, handleMove, stopDragging }
}

export default function Home() {
  const navigate = useNavigate()
  const [jdText, setJdText] = useState("")
  const [cvText, setCvText] = useState("")
  const [source, setSource] = useState<SessionSource>("jd")
  const [leetcodeUrl, setLeetcodeUrl] = useState("")
  const [pastProblemText, setPastProblemText] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fileDragging, setFileDragging] = useState(false)
  const [cvDragging, setCvDragging] = useState(false)
  const [difficulty, setDifficulty] = useState<Difficulty>("medium")
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const cvInputRef = useRef<HTMLInputElement>(null)
  const pip = useDraggable({ x: window.innerWidth - 320, y: 80 })

  // Pre-render status polling — show setup screen until clips are ready
  // isSettingUp: true until we confirm clips exist on disk (regardless of running flag)
  const [prerenderStatus, setPrerenderStatus] = useState<{ running: boolean; total: number; done: number } | null>(null)
  const [isSettingUp, setIsSettingUp] = useState(true)
  useEffect(() => {
    let cancelled = false
    const poll = async () => {
      try {
        const status = await api.getPrerenderStatus()
        if (cancelled) return

        // wav2lip disabled — don't block UI
        if (!status.running && status.total === 0) {
          setIsSettingUp(false)
          return
        }

        // Check manifest first — if clips already exist and we're not rendering, dismiss silently
        try {
          const manifest = await api.getScenarioManifest()
          if (manifest.clips.length > 0 && !status.running) {
            setIsSettingUp(false)
            return
          }
        } catch { /* ignore */ }

        // Only show the overlay if we're actively rendering
        if (status.running) {
          setPrerenderStatus(status)
          setTimeout(poll, 2000)
        } else {
          // Not running, no clips yet — backend task hasn't started (race), retry silently
          setTimeout(poll, 2000)
        }
      } catch {
        if (!cancelled) setTimeout(poll, 3000)
      }
    }
    void poll()
    return () => { cancelled = true }
  }, [])

  async function extractPdfText(file: File): Promise<string> {
    const bytes = await file.arrayBuffer()
    const loadingTask = pdfjsLib.getDocument({ data: bytes })
    const pdf = await loadingTask.promise
    const pagesToRead = Math.min(pdf.numPages, 20)
    const chunks: string[] = []

    for (let pageNumber = 1; pageNumber <= pagesToRead; pageNumber += 1) {
      const page = await pdf.getPage(pageNumber)
      const content = await page.getTextContent()
      const text = content.items
        .map((item) => ("str" in item ? item.str : ""))
        .filter(Boolean)
        .join(" ")
      if (text.trim()) chunks.push(text.trim())
    }
    return chunks.join("\n")
  }

  function isSupportedCvFile(file: File): boolean {
    const lower = file.name.toLowerCase()
    return (
      file.type.startsWith("text/") ||
      file.type === "application/pdf" ||
      lower.endsWith(".txt") ||
      lower.endsWith(".md") ||
      lower.endsWith(".pdf")
    )
  }

  async function readCvFile(file: File) {
    if (!isSupportedCvFile(file)) {
      setError("Unsupported CV format. Upload .txt/.md/.pdf, or paste CV text.")
      return
    }
    try {
      const lower = file.name.toLowerCase()
      const text =
        file.type === "application/pdf" || lower.endsWith(".pdf")
          ? await extractPdfText(file)
          : await file.text()
      if (!text.trim()) {
        setError("Could not extract text from CV file.")
        return
      }
      setCvText(text)
      setError(null)
    } catch (err) {
      console.error("PDF parse error:", err)
      setError(`Failed to read PDF: ${err instanceof Error ? err.message : String(err)}`)
    }
  }

  async function handleAnalyzeJD() {
    const jdPayload = cvText.trim()
      ? `${jdText.trim()}\n\nCandidate CV:\n${cvText.trim()}`
      : jdText.trim()
    const payload =
      source === "jd" ? jdPayload : source === "url" ? leetcodeUrl.trim() : pastProblemText.trim()
    if (!payload) return
    setLoading(true)
    setError(null)
    try {
      const res = await api.createSession(
        source,
        payload,
        difficulty,
        source === "jd" ? cvText.trim() || undefined : undefined,
      )
      // Navigate immediately — Session page polls for problem readiness
      navigate(`/session/${res.session_id}`, {
        state: {
          openingMessage: res.opening_message,
          problemStatement: res.problem?.statement ?? null,
          starterCode: res.starter_code ?? null,
        },
      })
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong")
    } finally {
      setLoading(false)
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
    if (text) {
      setJdText(text)
      return
    }
    const file = e.dataTransfer.files[0]
    if (file && file.type.startsWith("text/")) setJdText(await file.text())
  }

  async function handlePasteFromClipboard() {
    try {
      setJdText(await navigator.clipboard.readText())
      textareaRef.current?.focus()
    } catch {
      textareaRef.current?.focus()
    }
  }

  async function handleCvFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    await readCvFile(file)
    if (e.currentTarget) e.currentTarget.value = ""
  }

  function handleCvDragOver(e: React.DragEvent) {
    e.preventDefault()
    setCvDragging(true)
  }

  function handleCvDragLeave() {
    setCvDragging(false)
  }

  async function handleCvDrop(e: React.DragEvent) {
    e.preventDefault()
    setCvDragging(false)
    const file = e.dataTransfer.files[0]
    if (!file) return
    await readCvFile(file)
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
        <div />
      </header>

      <div className="flex flex-1 overflow-hidden">
        <Sidebar activePage="home" />

        {/* Full-screen setup overlay — blocks UI until pre-rendering is done */}
        {isSettingUp && prerenderStatus && (
          <div className="fixed inset-0 z-[200] flex items-center justify-center bg-background">
            <div className="flex flex-col items-center gap-6 max-w-md text-center px-6">
              <img src="/logo.jpg" alt="grillme" className="h-16 w-16 rounded-full" />
              <h2 className="text-xl font-bold text-on-surface">Setting up your interview environment</h2>
              <p className="text-sm text-on-surface-variant leading-relaxed">
                {prerenderStatus.total > 0
                  ? `First-time setup — pre-rendering ${prerenderStatus.total} video clips for instant playback. This only happens once.`
                  : "Starting up the avatar service, please wait…"}
              </p>
              {prerenderStatus.total > 0 && (
                <div className="w-full space-y-2">
                  <div className="w-full h-2 bg-surface-container-highest rounded-full overflow-hidden">
                    <div
                      className="h-full bg-primary rounded-full transition-all duration-700 ease-out"
                      style={{ width: `${(prerenderStatus.done / prerenderStatus.total) * 100}%` }}
                    />
                  </div>
                  <p className="text-xs text-on-surface-variant">
                    {prerenderStatus.done} / {prerenderStatus.total} clips ready
                  </p>
                </div>
              )}
              <div className="flex items-center gap-2 text-xs text-outline">
                <span className="material-symbols-outlined text-sm animate-spin">progress_activity</span>
                {prerenderStatus.done < prerenderStatus.total
                  ? `Rendering clip ${prerenderStatus.done + 1} of ${prerenderStatus.total}…`
                  : `All ${prerenderStatus.total} clips rendered — finishing up…`}
              </div>
            </div>
          </div>
        )}

        <div className="flex flex-1 overflow-hidden">
          <div className="w-1/2 border-r border-border bg-surface-container-low flex flex-col overflow-hidden">
            {/* Accordion header */}
            <div className="flex items-center justify-between px-4 py-2 bg-surface-container-low border-b border-border shrink-0">
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-on-surface uppercase tracking-widest">Interview Input</span>
              </div>
              <div className="inline-flex rounded-lg border border-outline-variant/30 bg-surface-container-lowest p-1 gap-1">
                <button onClick={() => setSource("jd")} className={cn("px-3 py-1 text-xs rounded-md transition-colors", source === "jd" ? "bg-primary/20 text-primary" : "text-on-surface-variant hover:text-on-surface")}>
                  Job Description
                </button>
                <button onClick={() => setSource("url")} className={cn("px-3 py-1 text-xs rounded-md transition-colors", source === "url" ? "bg-primary/20 text-primary" : "text-on-surface-variant hover:text-on-surface")}>
                  LeetCode Link
                </button>
                <button onClick={() => setSource("text")} className={cn("px-3 py-1 text-xs rounded-md transition-colors", source === "text" ? "bg-primary/20 text-primary" : "text-on-surface-variant hover:text-on-surface")}>
                  Past Problem
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto no-scrollbar flex flex-col min-h-0">
              <div className="p-4 flex flex-col gap-3 shrink-0">
                  {source === "jd" ? (
                    <div className="flex flex-col gap-3">
                      <div className="flex flex-col gap-1.5">
                        <div className="text-[10px] font-bold text-outline uppercase tracking-wider px-0.5">Job Description</div>
                        <div
                          className={cn(
                            "relative rounded-xl border-2 border-dashed transition-all duration-200 overflow-hidden",
                            fileDragging ? "border-primary bg-primary/5 scale-[0.99]" : jdText ? "border-outline-variant/30 bg-surface-container-lowest" : "border-outline-variant/20 bg-surface-container-lowest hover:border-outline-variant/40",
                          )}
                          style={{ minHeight: "160px" }}
                          onDragOver={handleDragOver}
                          onDragLeave={handleDragLeave}
                          onDrop={handleDrop}
                        >
                          {!jdText && !fileDragging && (
                            <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 pointer-events-none select-none">
                              <span className="material-symbols-outlined text-4xl text-outline/15" style={{ fontVariationSettings: "'FILL' 1" }}>upload_file</span>
                              <p className="text-[11px] text-outline/50">Drop a .txt file or type here</p>
                            </div>
                          )}
                          {!jdText && !fileDragging && (
                            <button className="absolute bottom-3 right-3 z-10 flex items-center gap-2 px-3 py-1.5 rounded-xl border border-outline-variant/30 bg-surface-container text-[11px] font-semibold text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface transition-all" onClick={handlePasteFromClipboard}>
                              <span className="material-symbols-outlined text-sm">content_paste</span>
                              Paste from clipboard
                            </button>
                          )}
                          {fileDragging && (
                            <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 pointer-events-none">
                              <span className="material-symbols-outlined text-4xl text-primary animate-bounce">move_to_inbox</span>
                              <p className="text-xs font-bold text-primary">Drop it here</p>
                            </div>
                          )}
                          <textarea ref={textareaRef} className="w-full resize-none bg-transparent font-mono text-xs text-on-surface placeholder:text-outline/30 focus:outline-none p-3" style={{ minHeight: "160px" }} placeholder="Paste job description here..." value={jdText} onChange={(e) => setJdText(e.target.value)} />
                        </div>
                      </div>
                      <div className="flex flex-col gap-1.5">
                        <div className="text-[10px] font-bold text-outline uppercase tracking-wider px-0.5">CV / Resume (Optional)</div>
                        <div className={cn("relative rounded-xl border transition-colors overflow-hidden", cvDragging ? "border-primary bg-primary/5" : "border-outline-variant/30 bg-transparent")} style={{ minHeight: "80px" }} onDragOver={handleCvDragOver} onDragLeave={handleCvDragLeave} onDrop={handleCvDrop} onClick={() => cvInputRef.current?.click()}>
                          <textarea value={cvText} onChange={(e) => setCvText(e.target.value)} placeholder="Paste CV text, or drag/drop/click to upload PDF/TXT/MD" className="w-full bg-transparent rounded-xl px-3 py-2 text-xs text-on-surface placeholder:text-outline focus:outline-none resize-none" style={{ minHeight: "80px" }} />
                          {!cvText.trim() && <div className="pointer-events-none absolute right-3 top-2 text-[10px] text-outline flex items-center gap-1"><span className="material-symbols-outlined text-sm">upload_file</span>Drop or click</div>}
                        </div>
                      </div>
                    </div>
                  ) : source === "url" ? (
                    <div className="flex flex-col gap-3">
                      <div className="flex flex-col gap-1.5">
                        <div className="text-[10px] font-bold text-outline uppercase tracking-wider px-0.5">LeetCode Problem URL</div>
                        <input value={leetcodeUrl} onChange={(e) => setLeetcodeUrl(e.target.value)} placeholder="https://leetcode.com/problems/..." className="h-11 rounded-xl border border-outline-variant/30 bg-surface-container-lowest px-3 font-mono text-xs text-on-surface placeholder:text-outline focus:outline-none" />
                      </div>
                      <div className="flex flex-col gap-1.5">
                        <div className="text-[10px] font-bold text-outline uppercase tracking-wider px-0.5">CV / Resume (Optional)</div>
                        <div className={cn("relative rounded-xl border transition-colors overflow-hidden", cvDragging ? "border-primary bg-primary/5" : "border-outline-variant/30 bg-transparent")} style={{ minHeight: "100px" }} onDragOver={handleCvDragOver} onDragLeave={handleCvDragLeave} onDrop={handleCvDrop} onClick={() => cvInputRef.current?.click()}>
                          <textarea value={cvText} onChange={(e) => setCvText(e.target.value)} placeholder="Paste CV text, or drag/drop/click to upload PDF/TXT/MD" className="w-full bg-transparent rounded-xl px-3 py-2 text-xs text-on-surface placeholder:text-outline focus:outline-none resize-none" style={{ minHeight: "100px" }} />
                          {!cvText.trim() && <div className="pointer-events-none absolute right-3 top-2 text-[10px] text-outline flex items-center gap-1"><span className="material-symbols-outlined text-sm">upload_file</span>Drop or click</div>}
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="flex flex-col gap-3">
                      <div className="flex flex-col gap-1.5">
                        <div className="text-[10px] font-bold text-outline uppercase tracking-wider px-0.5">Past Problem Text</div>
                        <textarea value={pastProblemText} onChange={(e) => setPastProblemText(e.target.value)} placeholder="Paste a previously used interview problem here..." className="rounded-xl border border-outline-variant/30 bg-surface-container-lowest px-3 py-2 font-mono text-xs text-on-surface placeholder:text-outline focus:outline-none resize-none" style={{ minHeight: "160px" }} />
                      </div>
                      <div className="flex flex-col gap-1.5">
                        <div className="text-[10px] font-bold text-outline uppercase tracking-wider px-0.5">CV / Resume (Optional)</div>
                        <div className={cn("relative rounded-xl border transition-colors overflow-hidden", cvDragging ? "border-primary bg-primary/5" : "border-outline-variant/30 bg-transparent")} style={{ minHeight: "100px" }} onDragOver={handleCvDragOver} onDragLeave={handleCvDragLeave} onDrop={handleCvDrop} onClick={() => cvInputRef.current?.click()}>
                          <textarea value={cvText} onChange={(e) => setCvText(e.target.value)} placeholder="Paste CV text, or drag/drop/click to upload PDF/TXT/MD" className="w-full bg-transparent rounded-xl px-3 py-2 text-xs text-on-surface placeholder:text-outline focus:outline-none resize-none" style={{ minHeight: "100px" }} />
                          {!cvText.trim() && <div className="pointer-events-none absolute right-3 top-2 text-[10px] text-outline flex items-center gap-1"><span className="material-symbols-outlined text-sm">upload_file</span>Drop or click</div>}
                        </div>
                      </div>
                    </div>
                  )}

                  <input ref={cvInputRef} type="file" accept=".pdf,.txt,.md,application/pdf,text/plain,text/markdown" className="hidden" onChange={handleCvFileChange} />

                  <div className="space-y-1.5">
                    <p className="text-[10px] font-bold text-outline uppercase tracking-wider px-0.5">Difficulty</p>
                    <div className="grid grid-cols-3 gap-2">
                      {(Object.entries(DIFFICULTY_PICKER_META) as [Difficulty, typeof DIFFICULTY_PICKER_META[Difficulty]][]).map(([key, meta]) => (
                        <button key={key} onClick={() => setDifficulty(key)} className={cn("flex flex-col items-center gap-1 py-2.5 rounded-xl border text-xs font-semibold transition-all", difficulty === key ? meta.active : meta.color)}>
                          <span className="material-symbols-outlined text-base" style={{ fontVariationSettings: "'FILL' 1" }}>{meta.icon}</span>
                          <span className="font-bold">{meta.label}</span>
                          <span className="text-[10px] opacity-70">{meta.desc}</span>
                        </button>
                      ))}
                    </div>
                  </div>

                  {error && <p className="text-error text-xs flex items-center gap-1.5 px-1"><span className="material-symbols-outlined text-sm">error</span>{error}</p>}

                  <button
                    className="w-full py-2.5 text-sm font-bold rounded-xl shimmer-gradient text-on-primary hover:opacity-90 transition-opacity active:scale-[0.98] disabled:opacity-30 disabled:pointer-events-none flex items-center justify-center gap-2"
                    onClick={handleAnalyzeJD}
                    disabled={loading || (source === "jd" && !jdText.trim()) || (source === "url" && !leetcodeUrl.trim()) || (source === "text" && !pastProblemText.trim())}
                  >
                    {loading ? <><span className="material-symbols-outlined text-sm animate-spin">progress_activity</span>Building problem…</> : <><span className="material-symbols-outlined text-sm">psychology</span>Start Interview</>}
                  </button>
                </div>
            </div>
          </div>

          <div className="w-1/2 flex flex-col bg-surface-container-lowest overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2 bg-surface-container-low border-b border-border shrink-0">
              <div className="flex items-center gap-2 px-3 py-1 bg-surface-container-highest rounded-lg text-xs font-semibold text-on-surface border border-outline-variant/20">
                <span className="w-2.5 h-2.5 bg-blue-400 rounded-full" />
                Python 3.13
              </div>
              <div className="flex gap-2">
                <button className="px-3 py-1 text-xs font-semibold rounded-lg bg-surface-container-highest text-on-surface-variant opacity-60 cursor-not-allowed">
                  Run Code
                </button>
                <button className="px-3 py-1 text-xs font-semibold rounded-lg bg-primary/20 text-primary opacity-60 cursor-not-allowed">
                  Run Tests
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-hidden">
              <div className="flex font-mono text-[13px] h-full">
                <div className="w-10 bg-surface-container-lowest text-outline/30 flex flex-col items-end pr-3 py-4 select-none text-xs shrink-0">
                  {Array.from({ length: 10 }, (_, i) => <span key={i} className="leading-[1.75rem]">{i + 1}</span>)}
                </div>
                <div className="flex-1 p-4 overflow-y-auto no-scrollbar text-sm leading-[1.75rem]">
                  <div className="text-outline/30 italic text-xs mb-3"># Code editor preview</div>
                  <div><span className="text-primary/50">class</span><span className="text-on-surface/30"> Solution:</span></div>
                  <div className="pl-8"><span className="text-primary/50">def</span><span className="text-on-surface/30"> solve(self) -&gt; None:</span></div>
                  <div className="pl-16 text-outline/25"># problem will appear in session</div>
                </div>
              </div>
            </div>

            <div className="h-[24%] border-t border-border flex flex-col shrink-0">
              <div className="flex items-center justify-between px-4 py-1.5 border-b border-border bg-surface-container-low shrink-0">
                <div className="flex gap-4">
                  <button className="text-[10px] font-bold uppercase tracking-widest text-primary border-b border-primary">Console</button>
                  <button className="text-[10px] font-bold uppercase tracking-widest text-outline">Test Results</button>
                </div>
              </div>
              <div className="flex-1 p-4 font-mono text-xs overflow-y-auto no-scrollbar text-outline/50 space-y-1">
                <div className="text-outline/25 italic">&gt; Terminal output will appear in session.</div>
              </div>
            </div>
          </div>

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
                <div className="w-1.5 h-1.5 rounded-full bg-primary/60 animate-pulse" />
                <span className="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">AI Interviewer</span>
              </div>
              <span className="material-symbols-outlined text-sm text-outline/50">drag_indicator</span>
            </div>
            <div className="relative bg-surface-container-low" style={{ aspectRatio: "4/3" }}>
              <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-surface-container to-surface-container-highest">
                <span
                  className="material-symbols-outlined text-7xl pip-idle"
                  style={{ fontVariationSettings: "'FILL' 1", color: "rgba(155,156,158,0.2)" }}
                >
                  face
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
