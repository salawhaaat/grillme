/**
 * useSTTWebSocket — microphone → backend WebSocket → transcript
 *
 * MediaRecorder sends 500 ms audio chunks over a WebSocket to the backend.
 * The backend (faster-whisper) transcribes every 3 s and streams results back.
 *
 * API:
 *   start()  — open mic + WebSocket
 *   stop()   — close mic + WebSocket, returns final accumulated transcript
 *   transcript   — live partial transcript (updates as backend sends results)
 *   isListening  — true while mic is open
 *   isSupported  — false on browsers without MediaRecorder / getUserMedia
 */

import { useCallback, useRef, useState } from "react"

const TIMESLICE_MS = 500   // how often MediaRecorder fires ondataavailable

function wsUrl(sessionId: number): string {
  const proto = window.location.protocol === "https:" ? "wss" : "ws"
  return `${proto}://${window.location.host}/api/stt/ws/${sessionId}`
}

function getBestMime(): string {
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/mp4",
  ]
  for (const m of candidates) {
    if (typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(m)) return m
  }
  return ""
}

export function useSTTWebSocket(sessionId: number) {
  const [transcript, setTranscript] = useState("")
  const [isListening, setIsListening] = useState(false)

  const wsRef       = useRef<WebSocket | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const streamRef   = useRef<MediaStream | null>(null)
  // Mirrors transcript state — always readable without stale closures
  const transcriptRef = useRef("")
  // Prevent concurrent open() calls during the async getUserMedia gap
  const openingRef  = useRef(false)

  const isSupported =
    typeof MediaRecorder !== "undefined" && !!navigator.mediaDevices?.getUserMedia

  /** Open mic + WebSocket and start streaming. Idempotent. */
  const start = useCallback(async () => {
    if (openingRef.current || wsRef.current || recorderRef.current) return
    openingRef.current = true

    // Reset transcript for new turn
    transcriptRef.current = ""
    setTranscript("")

    // 1 — request mic
    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false })
    } catch (err) {
      console.error("[STT] mic denied:", err)
      openingRef.current = false
      return
    }
    streamRef.current = stream

    // 2 — open WebSocket
    const ws = new WebSocket(wsUrl(sessionId))
    wsRef.current = ws

    ws.binaryType = "arraybuffer"

    ws.onopen = () => {
      const mimeType = getBestMime()

      // Tell backend the codec
      ws.send(JSON.stringify({ action: "init", mime: mimeType || "audio/webm" }))

      // 3 — start MediaRecorder
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
      recorderRef.current = recorder

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0 && ws.readyState === WebSocket.OPEN) {
          ws.send(e.data)
        }
      }

      recorder.start(TIMESLICE_MS)
      setIsListening(true)
      openingRef.current = false
    }

    ws.onerror = (e) => {
      console.error("[STT] WS error", e)
      openingRef.current = false
      _cleanup()
    }

    ws.onclose = () => {
      setIsListening(false)
      openingRef.current = false
    }

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data as string) as {
          transcript?: string
          final?: boolean
          error?: string
        }
        if (msg.error) {
          console.error("[STT] backend:", msg.error)
          return
        }
        if (msg.transcript) {
          // Append new words — backend sends each window's text independently
          const updated = (transcriptRef.current + " " + msg.transcript).trim()
          transcriptRef.current = updated
          setTranscript(updated)
        }
      } catch { /* ignore */ }
    }

    function _cleanup() {
      if (recorderRef.current?.state !== "inactive") {
        try { recorderRef.current?.stop() } catch { /* ignore */ }
      }
      recorderRef.current = null
      streamRef.current?.getTracks().forEach((t) => t.stop())
      streamRef.current = null
      wsRef.current = null
      setIsListening(false)
    }
  }, [sessionId])

  /** Stop mic + WebSocket. Returns final accumulated transcript synchronously. */
  const stop = useCallback((): string => {
    const final = transcriptRef.current.trim()

    // Stop recorder
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      try { recorderRef.current.stop() } catch { /* ignore */ }
    }
    recorderRef.current = null

    // Release mic
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null

    // Tell backend to flush + close
    if (wsRef.current) {
      if (wsRef.current.readyState === WebSocket.OPEN) {
        try {
          wsRef.current.send(JSON.stringify({ action: "stop" }))
          wsRef.current.close()
        } catch { /* ignore */ }
      }
      wsRef.current = null
    }

    openingRef.current = false
    setIsListening(false)

    // Clear for next turn
    transcriptRef.current = ""
    setTranscript("")

    return final
  }, [])

  return { transcript, transcriptRef, isListening, start, stop, isSupported }
}
