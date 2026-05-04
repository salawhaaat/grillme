import { useEffect, useRef, useState } from "react"
import { api } from "@/lib/api/client"

type JobStatus = "idle" | "pending" | "done" | "error"

interface VideoEntry {
  name: string
  path: string
  url: string
  size_kb: number
}

export default function AvatarTestPage() {
  const [text, setText] = useState("Hello! I'm your AI interviewer. Tell me a bit about yourself.")
  const [voice, setVoice] = useState("en-US-GuyNeural")
  const [jobId, setJobId] = useState<string | null>(null)
  const [status, setStatus] = useState<JobStatus>("idle")
  const [videoUrl, setVideoUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [log, setLog] = useState<string[]>([])
  const [videos, setVideos] = useState<VideoEntry[]>([])
  const [loadingVideos, setLoadingVideos] = useState(false)
  const pollerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const videoRef = useRef<HTMLVideoElement | null>(null)

  function addLog(msg: string) {
    setLog((prev) => [`${new Date().toISOString().slice(11, 23)} ${msg}`, ...prev].slice(0, 50))
  }

  async function handleRender() {
    if (!text.trim()) return
    setStatus("pending")
    setVideoUrl(null)
    setError(null)
    setJobId(null)
    addLog(`POST /avatar/render-test text="${text.slice(0, 40)}..."`)

    try {
      const { job_id } = await api.renderTest(text, voice)
      setJobId(job_id)
      addLog(`job started: ${job_id}`)
      startPolling(job_id)
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(msg)
      setStatus("error")
      addLog(`ERROR: ${msg}`)
    }
  }

  function startPolling(id: string) {
    if (pollerRef.current) clearInterval(pollerRef.current)
    let elapsed = 0
    pollerRef.current = setInterval(async () => {
      elapsed += 2
      try {
        const job = await api.getVideoJob(id)
        addLog(`poll status=${job.status} elapsed=${elapsed}s`)
        if (job.status === "done" && job.video_url) {
          clearInterval(pollerRef.current!)
          pollerRef.current = null
          setStatus("done")
          setVideoUrl(job.video_url)
          addLog(`video ready: ${job.video_url}`)
        } else if (job.status === "error" || elapsed >= 180) {
          clearInterval(pollerRef.current!)
          pollerRef.current = null
          setStatus("error")
          setError(job.error ?? "Timed out after 180s")
          addLog(`job failed: ${job.error ?? "timeout"}`)
        }
      } catch (e) {
        addLog(`poll error: ${e instanceof Error ? e.message : e}`)
      }
    }, 2000)
  }

  useEffect(() => () => { if (pollerRef.current) clearInterval(pollerRef.current) }, [])

  // Imperatively play video when url changes
  useEffect(() => {
    const el = videoRef.current
    if (!el || !videoUrl) return
    el.load()
    el.play().catch(() => {})
  }, [videoUrl])

  async function loadVideos() {
    setLoadingVideos(true)
    try {
      const { videos: v } = await api.listVideos()
      setVideos(v)
      addLog(`loaded ${v.length} videos from server`)
    } catch (e) {
      addLog(`listVideos error: ${e instanceof Error ? e.message : e}`)
    } finally {
      setLoadingVideos(false)
    }
  }

  const statusColor = {
    idle: "text-gray-400",
    pending: "text-yellow-400",
    done: "text-green-400",
    error: "text-red-400",
  }[status]

  return (
    <div className="min-h-screen bg-[#08090B] text-white p-6 font-mono">
      <h1 className="text-2xl font-bold mb-1">Avatar (Wav2Lip) Test</h1>
      <p className="text-gray-500 text-sm mb-6">Render a video without a session. Backend must have AVATAR_PROVIDER=wav2lip.</p>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left: render form */}
        <div className="space-y-4">
          <div>
            <label className="text-xs text-gray-400 uppercase tracking-widest block mb-1">Text to render</label>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={4}
              className="w-full bg-gray-900 border border-gray-700 rounded-lg p-3 text-sm text-white resize-none outline-none focus:border-blue-500"
            />
          </div>

          <div>
            <label className="text-xs text-gray-400 uppercase tracking-widest block mb-1">Voice</label>
            <select
              value={voice}
              onChange={(e) => setVoice(e.target.value)}
              className="bg-gray-900 border border-gray-700 rounded-lg p-2 text-sm text-white outline-none focus:border-blue-500"
            >
              <option value="en-US-GuyNeural">en-US-GuyNeural (male)</option>
              <option value="en-US-JennyNeural">en-US-JennyNeural (female)</option>
              <option value="en-GB-RyanNeural">en-GB-RyanNeural (UK male)</option>
            </select>
          </div>

          <button
            onClick={() => void handleRender()}
            disabled={status === "pending" || !text.trim()}
            className="w-full py-3 rounded-xl bg-blue-700 hover:bg-blue-600 disabled:opacity-40 disabled:cursor-not-allowed font-bold text-sm transition-colors"
          >
            {status === "pending" ? `Rendering… (${jobId?.slice(0, 8) ?? "?"})` : "Render Video"}
          </button>

          <p className={`text-sm ${statusColor}`}>
            Status: <strong>{status}</strong>
            {error && <span className="ml-2 text-red-400">— {error}</span>}
          </p>

          {/* Video player */}
          {videoUrl && (
            <div className="rounded-xl overflow-hidden border border-gray-700 bg-black">
              <video
                ref={videoRef}
                src={videoUrl}
                controls
                autoPlay
                className="w-full"
                onCanPlay={(e) => e.currentTarget.play().catch(() => {})}
              />
              <p className="text-xs text-gray-500 p-2">{videoUrl}</p>
            </div>
          )}
        </div>

        {/* Right: debug log + video list */}
        <div className="space-y-4">
          <div className="rounded-xl border border-gray-800 bg-gray-950 p-4 max-h-64 overflow-y-auto">
            <p className="text-xs text-gray-500 mb-2 uppercase tracking-widest">Debug Log</p>
            {log.length === 0
              ? <p className="text-gray-600 text-xs">No events yet</p>
              : log.map((l, i) => <p key={i} className="text-xs text-gray-400">{l}</p>)
            }
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs text-gray-400 uppercase tracking-widest">Generated Videos</p>
              <button
                onClick={() => void loadVideos()}
                disabled={loadingVideos}
                className="text-xs text-blue-400 hover:text-blue-300 disabled:opacity-40"
              >
                {loadingVideos ? "Loading…" : "Refresh"}
              </button>
            </div>
            <div className="space-y-1 max-h-96 overflow-y-auto">
              {videos.length === 0
                ? <p className="text-gray-600 text-xs">Click Refresh to list videos from server</p>
                : videos.map((v) => (
                  <div key={v.path} className="flex items-center justify-between rounded-lg border border-gray-800 bg-gray-900 px-3 py-2">
                    <div className="min-w-0">
                      <p className="text-xs text-white truncate">{v.name}</p>
                      <p className="text-[10px] text-gray-500">{v.size_kb} KB</p>
                    </div>
                    <button
                      onClick={() => { setVideoUrl(v.url); setStatus("done") }}
                      className="ml-3 text-xs text-blue-400 hover:text-blue-300 shrink-0"
                    >
                      Play
                    </button>
                  </div>
                ))
              }
            </div>
          </div>
        </div>
      </div>

      <div className="mt-6 flex gap-4 text-xs text-gray-600">
        <a href="/stt-test" className="hover:text-gray-400">← STT Test</a>
        <a href="/" className="hover:text-gray-400">← Home</a>
      </div>
    </div>
  )
}
