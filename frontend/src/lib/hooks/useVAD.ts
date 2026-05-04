/**
 * useVAD — browser-side Voice Activity Detection via Silero VAD v5.
 *
 * Creates the MicVAD once on mount, then pauses/resumes based on `enabled`.
 * Never destroys until the component unmounts.
 */

import { useEffect, useRef, useState } from "react"
import { MicVAD, type RealTimeVADOptions } from "@ricky0123/vad-web"

interface UseVADOptions {
  onSpeechEnd: (audio: Float32Array) => void
  onSpeechStart?: () => void
  enabled: boolean
}

export function useVAD({ onSpeechEnd, onSpeechStart, enabled }: UseVADOptions) {
  const [isListening, setIsListening] = useState(false)
  const [isSpeaking, setIsSpeaking] = useState(false)
  const vadRef = useRef<MicVAD | null>(null)
  const initializingRef = useRef(false)
  const enabledRef = useRef(enabled)
  enabledRef.current = enabled

  const onSpeechEndRef = useRef(onSpeechEnd)
  onSpeechEndRef.current = onSpeechEnd
  const onSpeechStartRef = useRef(onSpeechStart)
  onSpeechStartRef.current = onSpeechStart

  // Create VAD once on mount
  useEffect(() => {
    let cancelled = false

    async function init() {
      if (initializingRef.current) return
      initializingRef.current = true

      try {
        const vad = await MicVAD.new({
          baseAssetPath: "/vad/",
          model: "v5",
          ortConfig: (ort) => { ort.env.wasm.wasmPaths = "/vad/" },

          redemptionFrames: 8,
          positiveSpeechThreshold: 0.6,
          negativeSpeechThreshold: 0.4,
          minSpeechFrames: 5,
          preSpeechPadFrames: 3,

          onSpeechStart: () => {
            setIsSpeaking(true)
            onSpeechStartRef.current?.()
          },
          onSpeechEnd: (audio: Float32Array) => {
            setIsSpeaking(false)
            onSpeechEndRef.current(audio)
          },

          // Don't auto-start — we control via pause/start based on enabled
          startOnLoad: false,
        } as Partial<RealTimeVADOptions>)

        if (cancelled) {
          vad.destroy()
          return
        }

        // Ensure VAD is paused regardless of startOnLoad behaviour
        try { vad.pause() } catch { /* */ }
        vadRef.current = vad

        // If enabled was already true by the time init finishes, start
        if (enabledRef.current) {
          vad.start()
          setIsListening(true)
        }
      } catch (err) {
        console.error("[VAD] Failed to initialize:", err)
      } finally {
        initializingRef.current = false
      }
    }

    void init()

    // Destroy only on unmount
    return () => {
      cancelled = true
      const vad = vadRef.current
      if (vad) {
        try { vad.pause() } catch { /* */ }
        try { vad.destroy() } catch { /* */ }
        vadRef.current = null
      }
      setIsListening(false)
      setIsSpeaking(false)
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Pause/resume based on enabled prop (no destroy)
  // Guard against calling start() while VAD is still initializing
  useEffect(() => {
    const vad = vadRef.current
    if (!vad || initializingRef.current) return

    if (enabled) {
      try { vad.start() } catch { /* ignore if already started */ }
      setIsListening(true)
    } else {
      try { vad.pause() } catch { /* ignore if already paused */ }
      setIsListening(false)
    }
  }, [enabled])

  return { isListening, isSpeaking }
}

/**
 * Encode a Float32Array (16 kHz mono) as a WAV file (16-bit PCM).
 */
export function encodeWAV(samples: Float32Array): ArrayBuffer {
  const sampleRate = 16000
  const numChannels = 1
  const bitsPerSample = 16
  const byteRate = sampleRate * numChannels * (bitsPerSample / 8)
  const blockAlign = numChannels * (bitsPerSample / 8)
  const dataLength = samples.length * (bitsPerSample / 8)
  const totalLength = 44 + dataLength

  const buffer = new ArrayBuffer(totalLength)
  const view = new DataView(buffer)

  writeString(view, 0, "RIFF")
  view.setUint32(4, totalLength - 8, true)
  writeString(view, 8, "WAVE")
  writeString(view, 12, "fmt ")
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, numChannels, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, byteRate, true)
  view.setUint16(32, blockAlign, true)
  view.setUint16(34, bitsPerSample, true)
  writeString(view, 36, "data")
  view.setUint32(40, dataLength, true)

  let offset = 44
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]))
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true)
    offset += 2
  }
  return buffer
}

function writeString(view: DataView, offset: number, str: string) {
  for (let i = 0; i < str.length; i++) {
    view.setUint8(offset + i, str.charCodeAt(i))
  }
}
