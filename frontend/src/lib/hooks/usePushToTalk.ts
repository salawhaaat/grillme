/**
 * usePushToTalk — MediaRecorder-based push-to-talk hook.
 *
 * Hold to record, release to get a Blob. Prefers webm/opus → mp4 → browser default.
 * Cleans up the mic stream on unmount.
 */

import { useEffect, useRef, useState } from "react"

interface UsePushToTalkOptions {
  onError?: (message: string) => void
}

interface UsePushToTalkReturn {
  startRecording: () => Promise<void>
  stopRecording: () => Promise<Blob | null>
  isRecording: boolean
}

// MIME type preference order (Requirement 7.1)
const PREFERRED_TYPES = [
  "audio/webm;codecs=opus",
  "audio/mp4",
  "", // browser default
]

function selectMimeType(): string {
  return (
    PREFERRED_TYPES.find((t) => t === "" || MediaRecorder.isTypeSupported(t)) ?? ""
  )
}

export function usePushToTalk(options?: UsePushToTalkOptions): UsePushToTalkReturn {
  const [isRecording, setIsRecording] = useState(false)

  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const streamRef = useRef<MediaStream | null>(null)
  // Resolve function for the stopRecording promise — set in onstop handler
  const stopResolveRef = useRef<((blob: Blob) => void) | null>(null)

  // Cleanup on unmount (Requirement 1.8)
  useEffect(() => {
    return () => {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
        try { mediaRecorderRef.current.stop() } catch { /* ignore */ }
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop())
        streamRef.current = null
      }
    }
  }, [])

  async function startRecording(): Promise<void> {
    // No-op if already recording (Requirement 1.5)
    if (isRecording || mediaRecorderRef.current?.state === "recording") return

    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch (err) {
      // Permission denied or other getUserMedia error (Requirement 1.4)
      const msg =
        err instanceof Error && err.name === "NotAllowedError"
          ? "Microphone access was denied. Please allow microphone access and try again."
          : err instanceof Error
          ? `Microphone error: ${err.message}`
          : "Could not access microphone."
      options?.onError?.(msg)
      return
    }

    streamRef.current = stream
    chunksRef.current = []

    const mimeType = selectMimeType()
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
    mediaRecorderRef.current = recorder

    recorder.ondataavailable = (e: BlobEvent) => {
      if (e.data && e.data.size > 0) {
        chunksRef.current.push(e.data)
      }
    }

    recorder.onstop = () => {
      const blob = new Blob(chunksRef.current, {
        type: mimeType || "audio/webm",
      })
      chunksRef.current = []
      stopResolveRef.current?.(blob)
      stopResolveRef.current = null
    }

    recorder.start()
    setIsRecording(true)
  }

  async function stopRecording(): Promise<Blob | null> {
    // Return null if not recording (Requirement 1.6)
    if (!isRecording || !mediaRecorderRef.current || mediaRecorderRef.current.state === "inactive") {
      return null
    }

    return new Promise<Blob>((resolve) => {
      stopResolveRef.current = resolve

      // Stop all stream tracks to release the mic (Requirement 1.8)
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop())
        streamRef.current = null
      }

      try {
        mediaRecorderRef.current!.stop()
      } catch {
        // If stop() throws, resolve with empty blob
        stopResolveRef.current = null
        resolve(new Blob([], { type: "audio/webm" }))
      }

      mediaRecorderRef.current = null
      setIsRecording(false)
    })
  }

  return { startRecording, stopRecording, isRecording }
}
