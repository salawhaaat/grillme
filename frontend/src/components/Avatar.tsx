import { useMemo, useEffect, useRef, useState, type MouseEvent, type RefObject, type TouchEvent } from "react"
import { cn } from "@/lib/utils"

interface AvatarProps {
  speaking: boolean
  listening: boolean
  audioEnabled: boolean
  statusLabel: string
  pos: { x: number; y: number }
  personaText?: string
  provider?: "local" | "heygen"
  personaSeed?: string
  videoUrl?: string | null
  analyserRef: RefObject<AnalyserNode | null>
  onMouseDown: (e: MouseEvent) => void
  onTouchStart: (e: TouchEvent) => void
}

function hashString(input: string): number {
  let h = 0
  for (let i = 0; i < input.length; i += 1) {
    h = (h << 5) - h + input.charCodeAt(i)
    h |= 0
  }
  return Math.abs(h)
}

function extractPersonaName(personaText?: string): string {
  if (!personaText?.trim()) return "AI Interviewer"
  const byName = personaText.match(/(?:name is|I am|I'm)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)/)
  if (byName?.[1]) return byName[1]
  const firstWords = personaText.match(/\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?/)
  return firstWords?.[0] ?? "AI Interviewer"
}

export function Avatar({
  speaking,
  listening,
  audioEnabled,
  statusLabel,
  pos,
  personaText,
  provider = "local",
  personaSeed,
  videoUrl,
  analyserRef,
  onMouseDown,
  onTouchStart,
}: AvatarProps) {
  const rafRef = useRef<number | null>(null)
  const [mouthLevel, setMouthLevel] = useState(0)
  const [blinkClosed, setBlinkClosed] = useState(false)
  const [portraitFailed, setPortraitFailed] = useState(false)

  const seed = useMemo(() => hashString(personaText ?? "AI Interviewer"), [personaText])
  const visualSeed = personaSeed ?? String(seed)
  const personaName = useMemo(() => extractPersonaName(personaText), [personaText])

  const skinTones = ["#f2d1b3", "#e6bf95", "#d8ab85", "#c9966e", "#aa7f58"]
  const hairTones = ["#1e1a17", "#2a2320", "#3c2f2b", "#5b4638", "#101820"]
  const suitTones = ["#1f2937", "#273449", "#2e3a3a", "#3a2f4d", "#2f3e64"]

  const skin = skinTones[seed % skinTones.length]
  const hair = hairTones[(seed >> 3) % hairTones.length]
  const suit = suitTones[(seed >> 5) % suitTones.length]
  const jawRoundness = 2 + ((seed >> 8) % 4)
  const hairHeight = 17 + ((seed >> 11) % 9)
  const browTilt = ((seed >> 13) % 5) - 2

  useEffect(() => {
    let timeoutId: number | undefined

    function scheduleBlink() {
      const delay = 2800 + Math.random() * 2200
      timeoutId = window.setTimeout(() => {
        setBlinkClosed(true)
        window.setTimeout(() => setBlinkClosed(false), 130)
        scheduleBlink()
      }, delay)
    }

    scheduleBlink()
    return () => {
      if (timeoutId) window.clearTimeout(timeoutId)
    }
  }, [])

  useEffect(() => {
    if (!speaking) {
      setMouthLevel(0)
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current)
        rafRef.current = null
      }
      return
    }

    const analyser = analyserRef.current
    if (!analyser) {
      setMouthLevel(0.2)
      return
    }
    const buf = new Uint8Array(analyser.frequencyBinCount)

    const tick = () => {
      analyser.getByteTimeDomainData(buf)
      let maxDeviation = 0
      for (let i = 0; i < buf.length; i += 1) {
        const deviation = Math.abs(buf[i] - 128)
        if (deviation > maxDeviation) maxDeviation = deviation
      }
      setMouthLevel(maxDeviation / 128)
      rafRef.current = requestAnimationFrame(tick)
    }

    rafRef.current = requestAnimationFrame(tick)
    return () => {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current)
        rafRef.current = null
      }
    }
  }, [speaking, analyserRef])

  const eyeHeight = blinkClosed ? 1.2 : listening ? 4.6 : 3.2
  const mouthOpen = speaking && mouthLevel > 0.05
  const mouthHeight = mouthOpen ? Math.min(15, 3 + mouthLevel * 24) : 1.6
  const externalPortraitUrl = useMemo(
    () => `https://i.pravatar.cc/320?u=${encodeURIComponent(visualSeed)}`,
    [visualSeed],
  )

  return (
    <div
      className="fixed z-50 w-64 rounded-2xl overflow-hidden glass-panel shadow-2xl select-none touch-none"
      style={{ left: pos.x, top: pos.y }}
    >
      <div
        className="flex items-center justify-between px-3 py-2 bg-surface-container/90 cursor-grab active:cursor-grabbing border-b border-white/5"
        onMouseDown={onMouseDown}
        onTouchStart={onTouchStart}
      >
        <div className="flex items-center gap-2">
          <div className={cn("w-1.5 h-1.5 rounded-full animate-pulse", speaking ? "bg-primary" : listening ? "bg-blue-400" : "bg-outline/40")} />
          <span className="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">{personaName}</span>
          <span className="text-[9px] uppercase tracking-wider text-on-surface-variant/60">{provider}</span>
        </div>
        <div className="flex items-end gap-0.5">
          {(speaking || listening) && (speaking ? [0, 120, 240, 360, 480] : [0, 150, 300]).map((delay) => (
            <div key={delay} className={cn("w-0.5 rounded-full bar-wave", speaking ? "bg-primary" : "bg-blue-400")} style={{ animationDelay: `${delay}ms`, height: "8px" }} />
          ))}
        </div>
      </div>
      <div
        className="flex items-center justify-center h-5 bg-surface-container-high/90 border-b border-white/5 cursor-grab active:cursor-grabbing"
        onMouseDown={onMouseDown}
        onTouchStart={onTouchStart}
      >
        <div className="w-14 h-1 rounded-full bg-outline/50" />
      </div>
      <div className="relative bg-surface-container-low" style={{ aspectRatio: "4/3" }}>
        <div className="w-full h-full flex flex-col items-center justify-center gap-1.5 bg-gradient-to-br from-surface-container to-surface-container-highest">
          {provider !== "local" && videoUrl ? (
            <div className="relative w-36 h-36 rounded-full overflow-hidden border border-white/20 shadow-lg">
              <video
                src={videoUrl}
                className="w-full h-full object-cover"
                autoPlay
                playsInline
                muted
              />
              {(speaking || listening) && (
                <span className={cn("absolute inset-0 opacity-10", speaking ? "bg-primary" : "bg-blue-400")} />
              )}
            </div>
          ) : provider !== "local" && !portraitFailed ? (
            <div className="relative w-36 h-36 rounded-full overflow-hidden border border-white/20 shadow-lg">
              <img
                src={externalPortraitUrl}
                alt={personaName}
                className="w-full h-full object-cover"
                onError={() => setPortraitFailed(true)}
              />
              {(speaking || listening) && (
                <span className={cn("absolute inset-0 opacity-20", speaking ? "bg-primary" : "bg-blue-400")} />
              )}
            </div>
          ) : (
            <svg viewBox="0 0 160 160" className="w-32 h-32" aria-hidden="true">
            <ellipse cx="80" cy="150" rx="55" ry="24" fill={suit} opacity="0.95" />
            <rect x="42" y="108" width="76" height="45" rx="14" fill={suit} />

            <path
              d={`M45 ${60 - hairHeight / 6} Q 80 ${32 - hairHeight / 3} 115 ${60 - hairHeight / 6} L 110 94 Q 80 ${106 + jawRoundness} 50 94 Z`}
              fill={hair}
              opacity="0.98"
            />
            <ellipse cx="80" cy="82" rx={32 + jawRoundness} ry={38 - jawRoundness / 2} fill={skin} />

            <rect x={50} y={64 + browTilt} width="20" height="2.4" rx="1.2" fill={hair} opacity="0.75" />
            <rect x={90} y={64 - browTilt} width="20" height="2.4" rx="1.2" fill={hair} opacity="0.75" />
            <ellipse cx="60" cy="76" rx="5" ry={eyeHeight} fill={listening ? "#7dd3fc" : "#1f2937"} />
            <ellipse cx="100" cy="76" rx="5" ry={eyeHeight} fill={listening ? "#7dd3fc" : "#1f2937"} />

            <path d="M80 83 L76 96 L84 96 Z" fill="#bb8b66" opacity="0.5" />
            {mouthOpen ? (
              <ellipse cx="80" cy="108" rx="13" ry={mouthHeight / 2} fill="#9f3d2f" />
            ) : (
              <line x1="67" y1="108" x2="93" y2="108" stroke="#9f3d2f" strokeWidth="2.8" strokeLinecap="round" />
            )}
            </svg>
          )}
          <span
            className="text-[10px] uppercase tracking-widest font-semibold transition-colors duration-300"
            style={{
              color: speaking
                ? "rgba(224,90,58,0.7)"
                : listening
                ? "rgba(96,165,250,0.6)"
                : audioEnabled
                ? "rgba(155,156,158,0.3)"
                : "rgba(155,156,158,0.25)",
            }}
          >
            {statusLabel}
          </span>
        </div>
        {(speaking || listening) && (
          <span className={cn("absolute inset-0 animate-ping opacity-10", speaking ? "bg-primary" : "bg-blue-400")} />
        )}
      </div>
    </div>
  )
}
