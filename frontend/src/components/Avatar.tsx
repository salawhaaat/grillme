import { useMemo, useState, type MouseEvent, type RefObject, type TouchEvent } from "react"
import { cn } from "@/lib/utils"

interface AvatarProps {
  speaking: boolean
  listening: boolean
  audioEnabled: boolean
  statusLabel: string
  pos: { x: number; y: number }
  personaText?: string
  analyserRef: RefObject<AnalyserNode | null>
  onMouseDown: (e: MouseEvent) => void
  onTouchStart: (e: TouchEvent) => void
}

/** Extract a readable name from the persona description. */
function extractPersonaName(text?: string): string {
  if (!text?.trim()) return "AI Interviewer"
  const m =
    text.match(/(?:name is|I am|I'm)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)/) ??
    text.match(/\b([A-Z][a-z]{2,})\b/)
  return m?.[1] ?? "AI Interviewer"
}

/**
 * Infer gender from the persona description.
 * Returns "f" for female signals, "m" otherwise.
 */
function inferGender(text?: string): "m" | "f" {
  if (!text) return "m"
  const normalized = ` ${text.toLowerCase().replace(/[^\w\s]/g, " ")} `
  const femaleWords = [
    " she ", " her ", " hers ", "herself",
    " woman ", " female ", " lady ", " girl ",
    " ms ", " mrs ", " miss ",
    " jenny", " aria", " rachel", " emma", " sophia", " olivia",
    " sarah", " jessica", " emily", " ashley", " amanda", " megan",
    " hannah", " lisa", " angela", " diana", " helen", " kate",
  ]
  return femaleWords.some((w) => normalized.includes(w)) ? "f" : "m"
}

const PHOTO = {
  m: "/interviewer.jpg",
  f: "/interviewer-f.jpg",
} as const

export function Avatar({
  speaking,
  listening,
  audioEnabled,
  statusLabel,
  pos,
  personaText,
  onMouseDown,
  onTouchStart,
}: AvatarProps) {
  const personaName = useMemo(() => extractPersonaName(personaText), [personaText])
  const gender = useMemo(() => inferGender(personaText), [personaText])
  const photoSrc = PHOTO[gender]

  const initials = personaName
    .split(" ")
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase()

  const [imgFailed, setImgFailed] = useState(false)

  const ringClass = speaking
    ? "ring-2 ring-primary ring-offset-2 ring-offset-surface-container"
    : listening
    ? "ring-2 ring-blue-400 ring-offset-2 ring-offset-surface-container"
    : "ring-1 ring-white/10"

  return (
    <div
      className="fixed z-50 w-40 rounded-2xl overflow-hidden glass-panel shadow-2xl select-none touch-none"
      style={{ left: pos.x, top: pos.y }}
    >
      {/* ── Title bar / drag handle ── */}
      <div
        className="flex items-center justify-between px-3 py-2 bg-surface-container/90 cursor-grab active:cursor-grabbing border-b border-white/5"
        onMouseDown={onMouseDown}
        onTouchStart={onTouchStart}
      >
        <div className="flex items-center gap-2 min-w-0">
          <div
            className={cn(
              "w-1.5 h-1.5 shrink-0 rounded-full transition-colors duration-300",
              speaking
                ? "bg-primary animate-pulse"
                : listening
                ? "bg-blue-400 animate-pulse"
                : "bg-outline/40",
            )}
          />
          <span className="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant truncate">
            {personaName}
          </span>
        </div>

        {/* Animated audio bars */}
        <div className="flex items-end gap-px h-4 shrink-0 ml-2">
          {(speaking || listening) &&
            (speaking ? [0, 110, 220, 330, 440] : [0, 160, 320]).map((d) => (
              <div
                key={d}
                className={cn("w-0.5 rounded-full bar-wave", speaking ? "bg-primary" : "bg-blue-400")}
                style={{ animationDelay: `${d}ms`, height: "8px" }}
              />
            ))}
        </div>
      </div>

      {/* ── Grip stripe ── */}
      <div
        className="flex items-center justify-center h-3 bg-surface-container-high/80 border-b border-white/5 cursor-grab"
        onMouseDown={onMouseDown}
        onTouchStart={onTouchStart}
      >
        <div className="w-8 h-px rounded-full bg-outline/25" />
      </div>

      {/* ── Portrait ── */}
      <div className="relative" style={{ aspectRatio: "3/4" }}>
        <div className="w-full h-full bg-gradient-to-b from-surface-container to-surface-container-highest flex flex-col items-center justify-between py-5">

          <div className={cn("w-28 h-28 rounded-full overflow-hidden shadow-xl transition-all duration-300", ringClass)}>
            {!imgFailed ? (
              <img
                src={photoSrc}
                alt={personaName}
                className="w-full h-full object-cover object-top"
                onError={() => setImgFailed(true)}
              />
            ) : (
              // Initials fallback
              <div className="w-full h-full flex items-center justify-center text-2xl font-bold text-white bg-primary/80">
                {initials}
              </div>
            )}
          </div>

          <div className="flex flex-col items-center gap-1 px-3">
            <span className="text-[11px] font-semibold text-on-surface text-center leading-tight">
              {personaName}
            </span>
            <span
              className="text-[9px] uppercase tracking-widest font-medium transition-colors duration-300"
              style={{
                color: speaking
                  ? "rgba(224,90,58,0.9)"
                  : listening
                  ? "rgba(96,165,250,0.85)"
                  : audioEnabled
                  ? "rgba(155,156,158,0.5)"
                  : "rgba(155,156,158,0.3)",
              }}
            >
              {statusLabel}
            </span>
          </div>
        </div>

        {/* Ambient glow */}
        {(speaking || listening) && (
          <span
            className={cn(
              "absolute inset-0 animate-ping opacity-[0.07] pointer-events-none",
              speaking ? "bg-primary" : "bg-blue-400",
            )}
          />
        )}
      </div>
    </div>
  )
}
