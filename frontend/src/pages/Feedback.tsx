import { useState, useEffect, useMemo } from "react"
import { useParams, useNavigate } from "react-router-dom"
import { api, type Session, type Scorecard } from "@/lib/api/client"
import { cn, scoreColorText, scoreColorBg } from "@/lib/utils"
import { Sidebar } from "@/components/Sidebar"
import { DIFFICULTY_META } from "@/lib/constants/difficulty"

function ScoreBar({ score, max = 10 }: { score: number; max?: number }) {
  const pct = (score / max) * 100
  return (
    <div className="h-1.5 rounded-full bg-surface-container-highest overflow-hidden">
      <div
        className={cn("h-full rounded-full transition-all duration-700", scoreColorBg(score))}
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}

export default function FeedbackPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const sessionId = Number(id)

  const [session, setSession] = useState<Session | null>(null)
  const [scorecard, setScorecard] = useState<Scorecard | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showConversation, setShowConversation] = useState(false)

  useEffect(() => {
    api.getSession(sessionId)
      .then((s) => {
        setSession(s)
        if (s.scorecard) {
          setScorecard(s.scorecard)
        } else {
          return api.finishSession(sessionId).then((res) => setScorecard(res.scorecard))
        }
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load feedback"))
      .finally(() => setLoading(false))
  }, [sessionId])

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center gap-3 text-outline">
        <span className="material-symbols-outlined animate-spin">progress_activity</span>
        Generating feedback…
      </div>
    )
  }

  const userMessages = useMemo(
    () => (session?.messages ?? []).filter((m) => m.role === "user"),
    [session?.messages],
  )
  const aiMessages = useMemo(
    () => (session?.messages ?? []).filter((m) => m.role === "assistant"),
    [session?.messages],
  )

  if (error || !session || !scorecard) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <p className="text-error text-sm">{error ?? "No feedback available"}</p>
      </div>
    )
  }

  const diff = DIFFICULTY_META[session.difficulty]

  return (
    <div className="h-screen overflow-hidden flex flex-col bg-background">
      {/* Header */}
      <header className="flex justify-between items-center w-full px-6 py-3 border-b border-border bg-background shrink-0">
        <div className="flex items-center gap-2">
          <img src="/logo.jpg" alt="grillme" className="h-9 w-9 rounded-full" />
          <span className="text-xl font-black tracking-tighter uppercase font-wordmark"><span className="text-on-surface">grill</span><span className="text-primary">me</span></span>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate("/history")}
            className="flex items-center gap-1.5 text-xs font-medium text-outline hover:text-on-surface transition-colors"
          >
            <span className="material-symbols-outlined text-sm">arrow_back</span>
            History
          </button>
          <button
            onClick={() => navigate(`/session/${sessionId}/scorecard`)}
            className="px-3 py-1.5 text-xs font-semibold rounded-xl border border-outline-variant/30 text-on-surface-variant hover:bg-surface-container-high transition-colors"
          >
            Scorecard
          </button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <Sidebar activePage="history" />

        <main className="flex-1 overflow-y-auto no-scrollbar">
          <div className="max-w-3xl mx-auto p-6 space-y-6">
            {/* Title */}
            <div className="flex items-start justify-between gap-4">
              <div className="space-y-2">
                <h1 className="text-2xl font-headline font-extrabold tracking-tight text-on-surface">
                  Interview Feedback
                </h1>
                <div className="flex items-center gap-2 flex-wrap">
                  {session.company && session.role && (
                    <p className="text-sm text-on-surface-variant">
                      <span className="text-primary font-semibold">{session.role}</span>
                      {" at "}
                      <span className="text-on-surface font-semibold">{session.company}</span>
                    </p>
                  )}
                  {session.level && (
                    <span className="px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded bg-surface-container-highest text-on-surface-variant border border-outline-variant/30">
                      {session.level}
                    </span>
                  )}
                  <span className={cn("px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded border flex items-center gap-1", diff.color)}>
                    <span className="material-symbols-outlined text-xs" style={{ fontVariationSettings: "'FILL' 1" }}>{diff.icon}</span>
                    {diff.label}
                  </span>
                </div>
              </div>
              <div className="text-right shrink-0">
                <div className={cn(
                  "text-5xl font-black font-headline tabular-nums",
                  scoreColorText(scorecard.overall_score)
                )}>
                  {scorecard.overall_score}
                  <span className="text-xl text-outline font-normal">/10</span>
                </div>
              </div>
            </div>

            {/* Summary */}
            <div className="bg-surface-container rounded-xl border border-outline-variant/20 p-5">
              <p className="text-xs font-bold text-outline uppercase tracking-wider mb-3 flex items-center gap-1.5">
                <span className="material-symbols-outlined text-sm" style={{ fontVariationSettings: "'FILL' 1" }}>summarize</span>
                Overall Summary
              </p>
              <p className="text-sm text-on-surface leading-relaxed">
                {scorecard.summary ?? "Interview completed."}
              </p>
            </div>

            {/* Detailed section breakdown */}
            {(scorecard.sections?.length ?? 0) > 0 && (
              <div className="bg-surface-container rounded-xl border border-outline-variant/20 overflow-hidden">
                <div className="px-5 py-4 border-b border-outline-variant/20">
                  <h2 className="text-xs font-bold text-outline uppercase tracking-wider flex items-center gap-1.5">
                    <span className="material-symbols-outlined text-sm" style={{ fontVariationSettings: "'FILL' 1" }}>analytics</span>
                    Section Breakdown
                  </h2>
                </div>
                <div className="divide-y divide-outline-variant/10">
                  {(scorecard.sections ?? []).map((section) => (
                    <div key={section.name} className="px-5 py-4 space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-semibold text-on-surface">{section.name}</span>
                        <span className={cn("text-sm font-mono font-bold", scoreColorText(section.score))}>
                          {section.score}/10
                        </span>
                      </div>
                      <ScoreBar score={section.score} />
                      <p className="text-xs text-on-surface-variant leading-relaxed">{section.feedback}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Strengths & improvements side by side */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="bg-surface-container rounded-xl border border-outline-variant/20 p-5">
                <h2 className="text-xs font-bold text-green-400 uppercase tracking-wider flex items-center gap-1.5 mb-4">
                  <span className="material-symbols-outlined text-sm" style={{ fontVariationSettings: "'FILL' 1" }}>check_circle</span>
                  Strengths
                </h2>
                <ul className="space-y-3">
                  {scorecard.strengths.map((s, i) => (
                    <li key={i} className="flex gap-2 text-sm text-on-surface-variant leading-relaxed">
                      <span className="text-green-400 shrink-0 mt-0.5">•</span>
                      {s}
                    </li>
                  ))}
                </ul>
              </div>
              <div className="bg-surface-container rounded-xl border border-outline-variant/20 p-5">
                <h2 className="text-xs font-bold text-tertiary uppercase tracking-wider flex items-center gap-1.5 mb-4">
                  <span className="material-symbols-outlined text-sm" style={{ fontVariationSettings: "'FILL' 1" }}>trending_up</span>
                  To Improve
                </h2>
                <ul className="space-y-3">
                  {(scorecard.improvements ?? scorecard.areas_to_improve ?? []).map((s, i) => (
                    <li key={i} className="flex gap-2 text-sm text-on-surface-variant leading-relaxed">
                      <span className="text-tertiary shrink-0 mt-0.5">•</span>
                      {s}
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            {/* Interview stats */}
            <div className="grid grid-cols-3 gap-3">
              {[
                { label: "Your responses", value: userMessages.length, icon: "person" },
                { label: "AI questions", value: aiMessages.length, icon: "smart_toy" },
                { label: "Total exchanges", value: session.messages.length, icon: "forum" },
              ].map(({ label, value, icon }) => (
                <div key={label} className="bg-surface-container rounded-xl border border-outline-variant/20 p-4 text-center space-y-1">
                  <span className="material-symbols-outlined text-primary text-xl" style={{ fontVariationSettings: "'FILL' 1" }}>
                    {icon}
                  </span>
                  <p className="text-2xl font-headline font-bold text-on-surface">{value}</p>
                  <p className="text-[10px] text-outline uppercase tracking-wider">{label}</p>
                </div>
              ))}
            </div>

            {/* Conversation replay */}
            <div className="bg-surface-container rounded-xl border border-outline-variant/20 overflow-hidden">
              <button
                onClick={() => setShowConversation((v) => !v)}
                className="w-full px-5 py-4 flex items-center justify-between text-left hover:bg-surface-container-high transition-colors"
              >
                <span className="text-xs font-bold text-outline uppercase tracking-wider flex items-center gap-1.5">
                  <span className="material-symbols-outlined text-sm">forum</span>
                  Full Conversation Replay
                </span>
                <span className={cn(
                  "material-symbols-outlined text-sm text-outline transition-transform",
                  showConversation ? "rotate-180" : ""
                )}>
                  expand_more
                </span>
              </button>

              {showConversation && (
                <div className="px-5 pb-5 space-y-3 border-t border-outline-variant/20 pt-4 max-h-[400px] overflow-y-auto no-scrollbar">
                  {session.messages.map((msg, i) => (
                    <div key={i} className={cn("flex gap-2", msg.role === "user" ? "justify-end" : "justify-start")}>
                      {msg.role === "assistant" && (
                        <div className="w-6 h-6 rounded-full bg-primary/20 border border-primary/20 flex items-center justify-center shrink-0 mt-0.5">
                          <span className="material-symbols-outlined text-xs text-primary" style={{ fontVariationSettings: "'FILL' 1" }}>smart_toy</span>
                        </div>
                      )}
                      <div className={cn(
                        "max-w-[75%] px-3 py-2 rounded-xl text-xs leading-relaxed",
                        msg.role === "user"
                          ? "bg-primary/10 text-primary border border-primary/15 rounded-br-sm"
                          : "bg-surface-container-highest text-on-surface rounded-bl-sm"
                      )}>
                        {msg.content}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* CTA */}
            <button
              onClick={() => navigate("/")}
              className="w-full py-3 text-sm font-bold rounded-xl shimmer-gradient text-on-primary hover:opacity-90 transition-opacity"
            >
              Start a new interview
            </button>
          </div>
        </main>
      </div>
    </div>
  )
}
