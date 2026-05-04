/**
 * LipSyncAvatar — avatar photo with amplitude-driven visual effects.
 *
 * Reads RMS from StreamingAudioPlayer's AnalyserNode at 60fps via rAF
 * and directly updates DOM elements (glow ring, amplitude bar) without
 * going through React state — no re-renders, no lag.
 *
 * Contains:
 *   - The interviewer photo (<img>)
 *   - A glow ring div that pulses with speech amplitude
 *   - An amplitude bar below the photo for visual feedback
 */

import { useEffect, useRef } from "react"
import type { StreamingAudioPlayer } from "@/lib/StreamingAudioPlayer"

interface LipSyncAvatarProps {
  src: string
  playerRef: React.RefObject<StreamingAudioPlayer | null>
  speaking: boolean
}

export function LipSyncAvatar({ src, playerRef, speaking }: LipSyncAvatarProps) {
  const glowRef = useRef<HTMLDivElement>(null)
  const barRef = useRef<HTMLDivElement>(null)
  const rafRef = useRef<number>(0)
  const envRef = useRef(0)
  const ampRef = useRef(0)
  const speakingRef = useRef(speaking)
  speakingRef.current = speaking

  useEffect(() => {
    function tick() {
      let rawRMS = 0
      const player = playerRef.current
      if (speakingRef.current && player) {
        rawRMS = player.computeRMS()
      }

      // EMA smoothing
      const smoothed = ampRef.current * 0.8 + rawRMS * 0.2
      ampRef.current = smoothed

      // Asymmetric envelope: fast attack, slow release
      let env = envRef.current
      if (smoothed > env) {
        env = env * 0.3 + smoothed * 0.7
      } else {
        env = env * 0.88 + smoothed * 0.12
      }
      if (env < 0.01) env = 0
      envRef.current = env

      // Direct DOM updates (no React re-render)
      const glow = glowRef.current
      if (glow) {
        if (env > 0 && speakingRef.current) {
          const spread = 4 + env * 24
          const blur = 2 + env * 12
          const alpha = 0.2 + env * 0.6
          const scale = 1 + env * 0.06
          glow.style.boxShadow = `0 0 ${spread}px ${blur}px rgba(224,90,58,${alpha})`
          glow.style.transform = `scale(${scale})`
          glow.style.opacity = "1"
        } else {
          glow.style.boxShadow = "none"
          glow.style.transform = "scale(1)"
          glow.style.opacity = "0"
        }
      }

      const bar = barRef.current
      if (bar) {
        if (speakingRef.current) {
          bar.style.width = `${Math.min(100, env * 160)}%`
        } else {
          bar.style.width = "0%"
        }
      }

      rafRef.current = requestAnimationFrame(tick)
    }

    rafRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafRef.current)
  }, [playerRef])

  return (
    <div className="flex flex-col items-center gap-2">
      {/* Photo + glow ring container */}
      <div className="relative w-28 h-28">
        {/* Glow ring — updated directly by rAF, not React */}
        <div
          ref={glowRef}
          className="absolute inset-0 rounded-full pointer-events-none"
          style={{ transition: "box-shadow 60ms, transform 60ms", opacity: 0 }}
        />
        {/* Photo */}
        <div className="w-full h-full rounded-full overflow-hidden">
          <img
            src={src}
            alt="AI Interviewer"
            className="w-full h-full object-cover object-top"
          />
        </div>
      </div>

      {/* Amplitude bar — only visible during speech */}
      <div className="w-20 h-1.5 bg-white/5 rounded-full overflow-hidden">
        <div
          ref={barRef}
          className="h-full bg-primary rounded-full"
          style={{ width: "0%", transition: "width 60ms" }}
        />
      </div>
    </div>
  )
}
