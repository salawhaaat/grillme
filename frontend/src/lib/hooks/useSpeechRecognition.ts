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
  const [isListening, setIsListening] = useState(false)
  const recognitionRef = useRef<RecognitionLike | null>(null)
  const finalRef = useRef("")
  const startedRef = useRef(false)
  const desiredListeningRef = useRef(false)
  const restartTimerRef = useRef<number | null>(null)

  const Recognition = useMemo(
    () => window.SpeechRecognition ?? window.webkitSpeechRecognition,
    [],
  )
  const isSupported = Boolean(Recognition)

  useEffect(() => {
    if (!Recognition) return
    const recognition = new Recognition()
    recognition.continuous = true
    recognition.interimResults = true
    recognition.lang = "en-US"

    recognition.onstart = () => {
      startedRef.current = true
      setIsListening(true)
    }

    recognition.onresult = (event) => {
      let interim = ""
      for (let i = 0; i < event.results.length; i += 1) {
        const chunk = event.results[i][0]?.transcript ?? ""
        if (event.results[i].isFinal) {
          finalRef.current += chunk
        } else {
          interim += chunk
        }
      }
      setTranscript(`${finalRef.current}${interim}`.trim())
    }

    recognition.onerror = (event) => {
      startedRef.current = false
      setIsListening(false)
      const code = event?.error ?? ""
      const shouldRetry = !["not-allowed", "service-not-allowed", "audio-capture"].includes(code)
      if (!shouldRetry) {
        desiredListeningRef.current = false
        return
      }
      if (desiredListeningRef.current) {
        if (restartTimerRef.current) window.clearTimeout(restartTimerRef.current)
        restartTimerRef.current = window.setTimeout(() => {
          if (!recognitionRef.current || startedRef.current || !desiredListeningRef.current) return
          try {
            recognitionRef.current.start()
          } catch { /* ignore */ }
        }, 350)
      }
    }

    recognition.onend = () => {
      startedRef.current = false
      setIsListening(false)
      setTranscript(finalRef.current.trim())
      if (!desiredListeningRef.current) return
      if (restartTimerRef.current) window.clearTimeout(restartTimerRef.current)
      restartTimerRef.current = window.setTimeout(() => {
        if (!recognitionRef.current || startedRef.current || !desiredListeningRef.current) return
        try {
          recognition.start()
        } catch { /* ignore */ }
      }, 250)
    }

    recognitionRef.current = recognition
    return () => {
      desiredListeningRef.current = false
      if (restartTimerRef.current) {
        window.clearTimeout(restartTimerRef.current)
        restartTimerRef.current = null
      }
      recognition.stop()
      recognitionRef.current = null
    }
  }, [Recognition])

  const start = useCallback(() => {
    desiredListeningRef.current = true
    if (!recognitionRef.current) return
    if (startedRef.current) return
    finalRef.current = ""
    setTranscript("")
    if (restartTimerRef.current) {
      window.clearTimeout(restartTimerRef.current)
      restartTimerRef.current = null
    }
    try {
      recognitionRef.current.start()
    } catch { /* ignore */ }
  }, [])

  const stop = useCallback(() => {
    desiredListeningRef.current = false
    if (restartTimerRef.current) {
      window.clearTimeout(restartTimerRef.current)
      restartTimerRef.current = null
    }
    if (!recognitionRef.current || !startedRef.current) return
    try {
      recognitionRef.current.stop()
    } catch { /* ignore */ }
  }, [])

  return { transcript, isListening, start, stop, isSupported }
}
