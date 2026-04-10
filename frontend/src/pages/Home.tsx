import { useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import { api, type Difficulty, type SessionSource } from "@/lib/api/client"
import { cn } from "@/lib/utils"
import { Sidebar } from "@/components/Sidebar"
import { DIFFICULTY_PICKER_META } from "@/lib/constants/difficulty"
import * as pdfjsLib from "pdfjs-dist"

pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString()

export default function Home() {
  const navigate = useNavigate()
  const [source, setSource] = useState<SessionSource>("jd")
  const [content, setContent] = useState("")
  const [difficulty, setDifficulty] = useState<Difficulty>("medium")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fileDragging, setFileDragging] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  async function extractPdfText(file: File): Promise<string> {
    const bytes = await file.arrayBuffer()
    const loadingTask = pdfjsLib.getDocument({ data: bytes })
    const pdf = await loadingTask.promise
    const pagesToRead = Math.min(pdf.numPages, 20)
    const chunks: string[] = []

    for (let pageNumber = 1; pageNumber <= pagesToRead; pageNumber += 1) {
      const page = await pdf.getPage(pageNumber)
      const contentData = await page.getTextContent()
      const text = contentData.items
        .map((item) => ("str" in item ? item.str : ""))
        .filter(Boolean)
        .join(" ")
      if (text.trim()) chunks.push(text.trim())
    }
    return chunks.join("\n")
  }

  async function readInputFile(file: File) {
    try {
      const lower = file.name.toLowerCase()
      const text =
        file.type === "application/pdf" || lower.endsWith(".pdf")
          ? await extractPdfText(file)
          : await file.text()
      if (!text.trim()) {
        setError("Could not extract text from file.")
        return
      }
      setContent(text)
      setError(null)
    } catch {
      setError("Failed to read file.")
    }
  }

  function isContentValid(): boolean {
    const value = content.trim()
    if (!value) return false
    if (source === "url") return value.includes("leetcode.com/problems/")
    return true
  }

  async function handleStartInterview() {
    const value = content.trim()
    if (!value) return
    if (source === "url" && !value.includes("leetcode.com/problems/")) {
      setError("URL must contain leetcode.com/problems/")
      return
    }

    setLoading(true)
    setError(null)
    try {
      const res = await api.createSession(source, value, difficulty)
      navigate(`/session/${res.session_id}`, {
        state: {
          openingMessage: res.opening_message,
          problemStatement: res.problem.statement,
          starterCode: res.starter_code,
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
      setContent(text)
      return
    }
    const file = e.dataTransfer.files[0]
    if (!file) return
    await readInputFile(file)
  }

  async function handlePasteFromClipboard() {
    try {
      setContent(await navigator.clipboard.readText())
      textareaRef.current?.focus()
    } catch {
      textareaRef.current?.focus()
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
        <div />
      </header>

      <div className="flex flex-1 overflow-hidden">
        <Sidebar activePage="home" />
        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-[720px] px-6 py-8">
            <div className="rounded-2xl border border-outline-variant/30 bg-surface-container-low p-5 space-y-5">
              <div className="space-y-2">
                <h1 className="text-xl font-bold text-on-surface">Start Mock Interview</h1>
                <p className="text-sm text-on-surface-variant">
                  Choose a source, add problem content, and start instantly.
                </p>
              </div>

              <div className="space-y-2">
                <label className="text-xs font-bold text-outline uppercase tracking-wider">
                  Source
                </label>
                <select
                  value={source}
                  onChange={(e) => {
                    setSource(e.target.value as SessionSource)
                    setError(null)
                    setContent("")
                  }}
                  className="w-full rounded-xl border border-outline-variant/30 bg-surface-container-lowest px-3 py-2 text-sm text-on-surface focus:outline-none focus:border-primary/50"
                >
                  <option value="jd">From Job Description</option>
                  <option value="url">From LeetCode URL</option>
                  <option value="text">From Problem Text</option>
                </select>
              </div>

              {source === "url" ? (
                <div className="space-y-2">
                  <label className="text-xs font-bold text-outline uppercase tracking-wider">
                    LeetCode URL
                  </label>
                  <input
                    type="text"
                    value={content}
                    onChange={(e) => setContent(e.target.value)}
                    placeholder="https://leetcode.com/problems/two-sum/"
                    className="w-full rounded-xl border border-outline-variant/30 bg-surface-container-lowest px-3 py-2 text-sm text-on-surface placeholder:text-outline focus:outline-none focus:border-primary/50"
                  />
                </div>
              ) : (
                <div className="space-y-2">
                  <label className="text-xs font-bold text-outline uppercase tracking-wider">
                    {source === "jd" ? "Job Description" : "Problem Text"}
                  </label>
                  <div
                    className={cn(
                      "relative rounded-xl border-2 border-dashed transition-all duration-200 overflow-hidden min-h-[320px]",
                      fileDragging
                        ? "border-primary bg-primary/5"
                        : content
                        ? "border-outline-variant/30 bg-surface-container-lowest"
                        : "border-outline-variant/20 bg-surface-container-lowest hover:border-outline-variant/40",
                    )}
                    onDragOver={handleDragOver}
                    onDragLeave={handleDragLeave}
                    onDrop={handleDrop}
                  >
                    {!content && !fileDragging && source === "jd" && (
                      <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 pointer-events-none select-none">
                        <span className="material-symbols-outlined text-5xl text-outline/25" style={{ fontVariationSettings: "'FILL' 1" }}>
                          upload_file
                        </span>
                        <div className="text-center space-y-1">
                          <p className="text-sm font-semibold text-on-surface-variant">Drop a file here</p>
                          <p className="text-xs text-outline">or paste / type below</p>
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
                      value={content}
                      onChange={(e) => setContent(e.target.value)}
                      placeholder={source === "jd" ? "Paste job description here..." : "Paste the problem description..."}
                      className={cn(
                        "w-full min-h-[320px] resize-y bg-transparent p-4 font-mono text-xs text-on-surface placeholder:text-outline/30 focus:outline-none",
                        !content && !fileDragging && source === "jd" ? "opacity-0 pointer-events-none" : "opacity-100",
                      )}
                    />
                  </div>
                </div>
              )}

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
                      <span className="material-symbols-outlined text-base" style={{ fontVariationSettings: "'FILL' 1" }}>
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
                onClick={handleStartInterview}
                disabled={loading || !isContentValid()}
              >
                {loading ? (
                  <>
                    <span className="material-symbols-outlined text-sm animate-spin">progress_activity</span>
                    Starting interview…
                  </>
                ) : (
                  <>
                    <span className="material-symbols-outlined text-sm">play_arrow</span>
                    Start Interview
                  </>
                )}
              </button>
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
