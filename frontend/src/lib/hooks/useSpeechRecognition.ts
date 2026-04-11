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
  onerror: (() => void) | null
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

    recognition.onerror = () => {
      setIsListening(false)
    }

    recognition.onend = () => {
      setIsListening(false)
      setTranscript(finalRef.current.trim())
    }

    recognitionRef.current = recognition
    return () => {
      recognition.stop()
      recognitionRef.current = null
    }
  }, [Recognition])

  const start = useCallback(() => {
    if (!recognitionRef.current || isListening) return
    finalRef.current = ""
    setTranscript("")
    recognitionRef.current.start()
  }, [isListening])

  const stop = useCallback(() => {
    if (!recognitionRef.current || !isListening) return
    recognitionRef.current.stop()
  }, [isListening])

  return { transcript, isListening, start, stop, isSupported }
}
