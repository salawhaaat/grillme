import { useState, useEffect } from "react"
import { useParams, useNavigate } from "react-router-dom"
import { api, type Scorecard, type Session } from "@/lib/api/client"
import { cn, scoreColorText, scoreColorBg } from "@/lib/utils"

function ScoreRing({ score }: { score: number }) {
  return (
    <div className={cn("text-6xl font-black font-headline tabular-nums leading-none", scoreColorText(score))}>
      {score}
      <span className="text-2xl text-outline font-normal">/10</span>
    </div>
  )
}

function SectionBar({ name, score, feedback }: { name: string; score: number; feedback: string }) {
  return (
    <div className="space-y-1.5">
      <div className="flex justify-between items-center text-xs">
        <span className="font-semibold text-on-surface uppercase tracking-wider">{name}</span>
        <span className="text-outline font-mono">{score}/10</span>
      </div>
      <div className="h-1.5 rounded-full bg-surface-container-highest overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all duration-700", scoreColorBg(score))}
          style={{ width: `${score * 10}%` }}
        />
      </div>
      <p className="text-xs text-on-surface-variant leading-relaxed">{feedback}</p>
    </div>
  )
}

export default function ScorecardPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const sessionId = Number(id)

  const [session, setSession] = useState<Session | null>(null)
  const [scorecard, setScorecard] = useState<Scorecard | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .getSession(sessionId)
      .then((s) => {
        setSession(s)
        if (s.scorecard) {
          setScorecard(s.scorecard)
        } else {
          return api
            .finishSession(sessionId)
            .then((res) => setScorecard(res.scorecard))
        }
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Failed to load scorecard"),
      )
      .finally(() => setLoading(false))
  }, [sessionId])

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex flex-col items-center justify-center gap-4">
        <span className="material-symbols-outlined text-5xl text-outline/30 animate-spin">
          progress_activity
        </span>
        <p className="text-outline text-sm">Generating scorecard…</p>
      </div>
    )
  }

  if (error || !scorecard) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <p className="text-error text-sm">{error ?? "No scorecard available"}</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Header */}
      <header className="flex justify-between items-center w-full px-6 py-3 border-b border-border bg-background">
        <div className="flex items-center gap-2">
          <img src="/logo.jpg" alt="grillme" className="h-9 w-9 rounded-full" />
          <span className="text-xl font-black tracking-tighter uppercase font-wordmark"><span className="text-on-surface">grill</span><span className="text-primary">me</span></span>
        </div>
        <button
          onClick={() => navigate("/")}
          className="flex items-center gap-1.5 text-xs font-medium text-outline hover:text-on-surface transition-colors"
        >
          <span className="material-symbols-outlined text-sm">arrow_back</span>
          New interview
        </button>
      </header>

      <div className="flex-1 p-6">
        <div className="max-w-2xl mx-auto space-y-5">
          {/* Score header card */}
          <div className="bg-surface-container rounded-xl border border-outline-variant/20 overflow-hidden">
            <div className="p-6 flex items-start justify-between">
              <div className="space-y-2">
                <h1 className="text-2xl font-headline font-extrabold tracking-tight text-on-surface">
                  Interview Scorecard
                </h1>
                <div className="flex items-center gap-2 flex-wrap">
                  {session?.company && session?.role && (
                    <p className="text-sm text-on-surface-variant">
                      <span className="text-primary font-semibold">{session.role}</span>
                      {" at "}
                      <span className="text-on-surface font-semibold">{session.company}</span>
                    </p>
                  )}
                  {session?.level && (
                    <span className="px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded bg-tertiary-container/20 text-tertiary border border-tertiary/30">
                      {session.level}
                    </span>
                  )}
                </div>
              </div>
              <ScoreRing score={scorecard.overall_score} />
            </div>
            <div className="px-6 pb-6">
              <p className="text-sm text-on-surface-variant leading-relaxed">
                {scorecard.summary}
              </p>
            </div>
          </div>

          {/* Section breakdown */}
          {scorecard.sections?.length > 0 && (
            <div className="bg-surface-container rounded-xl border border-outline-variant/20 p-6 space-y-5">
              <h2 className="text-xs font-bold uppercase tracking-widest text-outline">
                Breakdown
              </h2>
              {scorecard.sections.map((s) => (
                <SectionBar key={s.name} {...s} />
              ))}
            </div>
          )}

          {/* Strengths & Improvements */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="bg-surface-container rounded-xl border border-outline-variant/20 p-5">
              <h2 className="text-xs font-bold uppercase tracking-widest text-green-400 flex items-center gap-1.5 mb-4">
                <span className="material-symbols-outlined text-sm" style={{ fontVariationSettings: "'FILL' 1" }}>
                  check_circle
                </span>
                Strengths
              </h2>
              <ul className="space-y-2.5">
                {scorecard.strengths.map((s, i) => (
                  <li key={i} className="text-sm text-on-surface-variant flex gap-2 leading-relaxed">
                    <span className="text-green-400 mt-0.5 shrink-0">•</span>
                    {s}
                  </li>
                ))}
              </ul>
            </div>

            <div className="bg-surface-container rounded-xl border border-outline-variant/20 p-5">
              <h2 className="text-xs font-bold uppercase tracking-widest text-tertiary flex items-center gap-1.5 mb-4">
                <span className="material-symbols-outlined text-sm" style={{ fontVariationSettings: "'FILL' 1" }}>
                  trending_up
                </span>
                To improve
              </h2>
              <ul className="space-y-2.5">
                {scorecard.improvements.map((s, i) => (
                  <li key={i} className="text-sm text-on-surface-variant flex gap-2 leading-relaxed">
                    <span className="text-tertiary mt-0.5 shrink-0">•</span>
                    {s}
                  </li>
                ))}
              </ul>
            </div>
          </div>

          <button
            onClick={() => navigate("/")}
            className="w-full py-3 text-sm font-bold rounded-xl shimmer-gradient text-on-primary hover:opacity-90 transition-opacity active:scale-[0.98]"
          >
            Start a new interview
          </button>
        </div>
      </div>
    </div>
  )
}
