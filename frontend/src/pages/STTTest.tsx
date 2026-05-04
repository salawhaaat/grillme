import { useState } from "react"
import { usePushToTalk } from "@/lib/hooks/usePushToTalk"
import { api } from "@/lib/api/client"

export default function STTTestPage() {
  const [transcript, setTranscript] = useState("")
  const [status, setStatus] = useState("Ready — hold the button to record")
  const [log, setLog] = useState<string[]>([])

  function addLog(msg: string) {
    setLog((prev) => [...prev, `${new Date().toISOString().slice(11, 23)} ${msg}`])
  }

  const { startRecording, stopRecording, isRecording } = usePushToTalk({
    onError: (msg) => { setStatus(`Error: ${msg}`); addLog(`ERROR: ${msg}`) },
  })

  async function handleStart() {
    setStatus("Recording…")
    addLog("startRecording()")
    await startRecording()
  }

  async function handleStop() {
    setStatus("Sending to STT…")
    addLog("stopRecording() — waiting for blob")
    const blob = await stopRecording()
    if (!blob) {
      setStatus("No audio blob")
      addLog("blob is null")
      return
    }
    addLog(`blob ready: ${blob.size}B type=${blob.type}`)
    try {
      const text = await api.sttOneshot(blob)
      addLog(`STT response: "${text}"`)
      setTranscript(text || "(empty)")
      setStatus(text ? "Done" : "STT returned empty string")
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      setStatus(`STT error: ${msg}`)
      addLog(`STT error: ${msg}`)
    }
  }

  return (
    <div className="min-h-screen bg-[#08090B] text-white flex flex-col items-center justify-center gap-8 p-8 font-mono">
      <h1 className="text-2xl font-bold">STT Test Page</h1>
      <p className="text-gray-400 text-sm">{status}</p>

      <button
        onMouseDown={() => void handleStart()}
        onMouseUp={() => void handleStop()}
        onTouchStart={() => void handleStart()}
        onTouchEnd={() => void handleStop()}
        className={`w-32 h-32 rounded-full border-4 text-sm font-bold select-none transition-all ${
          isRecording
            ? "bg-red-600 border-red-400 scale-110 shadow-lg shadow-red-500/40"
            : "bg-blue-700 border-blue-400 hover:bg-blue-600"
        }`}
      >
        {isRecording ? "● REC" : "HOLD\nTO SPEAK"}
      </button>

      {transcript && (
        <div className="max-w-lg w-full rounded-xl border border-gray-700 bg-gray-900 p-4">
          <p className="text-xs text-gray-500 mb-1 uppercase tracking-widest">Transcript</p>
          <p className="text-lg text-green-400">{transcript}</p>
        </div>
      )}

      <div className="max-w-lg w-full rounded-xl border border-gray-800 bg-gray-950 p-4 max-h-64 overflow-y-auto">
        <p className="text-xs text-gray-500 mb-2 uppercase tracking-widest">Debug Log</p>
        {log.length === 0
          ? <p className="text-gray-600 text-xs">No events yet</p>
          : log.map((l, i) => <p key={i} className="text-xs text-gray-400">{l}</p>)
        }
      </div>

      <a href="/" className="text-xs text-gray-600 hover:text-gray-400">← Back to home</a>
    </div>
  )
}
