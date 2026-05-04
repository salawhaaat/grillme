import { useCallback, useEffect, useMemo, useRef, useState } from "react"

type RecognitionLike = {
  continuous: boolean
  interimResults: boolean
  lang: string
  start: () => void
  stop: () => void
  onresult: ((event: SpeechRecognitionEventLike) => void) | null
  onstart: (() => void) | null
  onend: (() => void) | null
  onerror: ((event: { error?: string }) => void) | null
}

type SpeechRecognitionEventLike = {
  results: ArrayLike<{
    isFinal: boolean
    0: { transcript: string }
    length: number
    item: (index: number) => { transcript: string }
  }>
}

type RecognitionCtor = new () => RecognitionLike

declare global {
  interface Window {
    SpeechRecognition?: RecognitionCtor
    webkitSpeechRecognition?: RecognitionCtor
  }
}

export function useSpeechRecognition() {
  const [transcript, setTranscript] = useState("")
  // isListening stays true across the brief browser-enforced restart gap so the UI
  // doesn't flicker. It only becomes false when stop() is explicitly called.
  const [isListening, setIsListening] = useState(false)

  const recognitionRef = useRef<RecognitionLike | null>(null)
  const finalRef = useRef("")
  const startedRef = useRef(false)          // recognition.start() has been called and onstart fired
  const desiredRef = useRef(false)          // caller wants listening to be active
  const restartTimerRef = useRef<number | null>(null)

  const Recognition = useMemo(
    () => window.SpeechRecognition ?? window.webkitSpeechRecognition,
    [],
  )
  const isSupported = Boolean(Recognition)

  useEffect(() => {
    if (!Recognition) return

    const recognition = new Recognition()
    recognition.continuous = false   // let each utterance end naturally; we restart manually
    recognition.interimResults = true
    recognition.lang = "en-US"

    recognition.onstart = () => {
      startedRef.current = true
      // Don't set isListening here — we set it in start() immediately so there's no gap
    }

    recognition.onresult = (event) => {
      let interim = ""
      for (let i = 0; i < event.results.length; i += 1) {
        const chunk = event.results[i][0]?.transcript ?? ""
        if (event.results[i].isFinal) {
          finalRef.current += chunk + " "
        } else {
          interim += chunk
        }
      }
      setTranscript(`${finalRef.current}${interim}`.trim())
    }

    recognition.onerror = (event) => {
      startedRef.current = false
      const code = event?.error ?? ""
      // Permanent errors — user denied mic or no hardware
      if (["not-allowed", "service-not-allowed", "audio-capture"].includes(code)) {
        desiredRef.current = false
        setIsListening(false)
        return
      }
      // no-speech is not an error — just restart quietly
      if (desiredRef.current) {
        scheduleRestart(300)
      }
    }

    recognition.onend = () => {
      startedRef.current = false
      // Snapshot final transcript when a recognition session ends
      setTranscript(finalRef.current.trim())
      // Restart immediately if still desired — keep isListening=true throughout
      if (desiredRef.current) {
        scheduleRestart(150)
      } else {
        setIsListening(false)
      }
    }

    recognitionRef.current = recognition

    return () => {
      desiredRef.current = false
      clearRestartTimer()
      try { recognition.stop() } catch { /* ignore */ }
      recognitionRef.current = null
      startedRef.current = false
    }
  }, [Recognition]) // eslint-disable-line react-hooks/exhaustive-deps

  function clearRestartTimer() {
    if (restartTimerRef.current !== null) {
      window.clearTimeout(restartTimerRef.current)
      restartTimerRef.current = null
    }
  }

  function scheduleRestart(delay: number) {
    clearRestartTimer()
    restartTimerRef.current = window.setTimeout(() => {
      restartTimerRef.current = null
      if (!recognitionRef.current || startedRef.current || !desiredRef.current) return
      try {
        recognitionRef.current.start()
      } catch { /* ignore — already started */ }
    }, delay)
  }

  const start = useCallback(() => {
    if (desiredRef.current && (startedRef.current || restartTimerRef.current !== null)) {
      // Already listening or about to — nothing to do
      return
    }
    const fresh = !desiredRef.current
    desiredRef.current = true
    setIsListening(true)

    if (fresh) {
      // New listening session — clear accumulated transcript
      finalRef.current = ""
      setTranscript("")
    }

    clearRestartTimer()
    if (!recognitionRef.current || startedRef.current) return
    try {
      recognitionRef.current.start()
    } catch { /* ignore */ }
  }, [])

  const stop = useCallback(() => {
    desiredRef.current = false
    clearRestartTimer()
    setIsListening(false)
    finalRef.current = ""
    setTranscript("")
    if (!recognitionRef.current || !startedRef.current) return
    try {
      recognitionRef.current.stop()
    } catch { /* ignore */ }
  }, [])

  const resetTranscript = useCallback(() => {
    finalRef.current = ""
    setTranscript("")
  }, [])

  return { transcript, isListening, start, stop, resetTranscript, isSupported }
}
