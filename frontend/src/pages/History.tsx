import { useState, useEffect, useMemo } from "react"
import { useNavigate } from "react-router-dom"
import { api, type SessionListItem } from "@/lib/api/client"
import { cn, scoreColorText } from "@/lib/utils"
import { Sidebar } from "@/components/Sidebar"
import { DIFFICULTY_META } from "@/lib/constants/difficulty"

function ScoreBadge({ score }: { score: number | null }) {
  if (score === null) {
    return (
      <span className="text-xs font-mono text-outline">—</span>
    )
  }
  return (
    <span className={cn("text-2xl font-black font-headline tabular-nums", scoreColorText(score))}>
      {score}
      <span className="text-xs font-normal text-outline">/10</span>
    </span>
  )
}

function SessionCard({ session, onClick, onFeedback, onDelete }: {
  session: SessionListItem
  onClick: () => void
  onFeedback: () => void
  onDelete: () => void
}) {
  const diff = DIFFICULTY_META[session.difficulty]
  const date = new Date(session.created_at).toLocaleDateString("en-US", {
    month: "short", day: "numeric", year: "numeric",
  })
  const isFinished = session.finished_at !== null

  return (
    <div className="bg-surface-container rounded-xl border border-outline-variant/20 hover:border-outline-variant/40 transition-all group overflow-hidden">
      <div className="p-5 flex items-start justify-between gap-4">
        {/* Left: info */}
        <div className="flex-1 min-w-0 space-y-3">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="font-headline font-bold text-on-surface tracking-tight truncate">
              {session.role ?? "Unknown Role"}
            </h3>
            {session.company && (
              <span className="text-xs text-on-surface-variant">@ {session.company}</span>
            )}
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            {session.level && (
              <span className="px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded bg-surface-container-highest text-on-surface-variant border border-outline-variant/30">
                {session.level}
              </span>
            )}
            <span className={cn(
              "px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded border flex items-center gap-1",
              diff.color
            )}>
              <span className="material-symbols-outlined text-xs" style={{ fontVariationSettings: "'FILL' 1" }}>
                {diff.icon}
              </span>
              {diff.label}
            </span>
            <span className={cn(
              "px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded border",
              isFinished
                ? "text-green-400 bg-green-400/10 border-green-400/20"
                : "text-outline bg-surface-container-highest border-outline-variant/30"
            )}>
              {isFinished ? "Completed" : "In Progress"}
            </span>
          </div>

          <div className="flex items-center gap-4 text-xs text-outline">
            <span className="flex items-center gap-1">
              <span className="material-symbols-outlined text-sm">chat_bubble</span>
              {session.message_count} messages
            </span>
            <span className="flex items-center gap-1">
              <span className="material-symbols-outlined text-sm">calendar_today</span>
              {date}
            </span>
          </div>
        </div>

        {/* Right: score */}
        <div className="flex flex-col items-end gap-3 shrink-0">
          <ScoreBadge score={session.overall_score} />
          <div className="flex gap-2">
            {isFinished && (
              <button
                onClick={(e) => { e.stopPropagation(); onFeedback() }}
                className="px-3 py-1.5 text-xs font-semibold rounded-lg border border-primary/30 text-primary hover:bg-primary/10 transition-colors"
              >
                Feedback
              </button>
            )}
            <button
              onClick={(e) => { e.stopPropagation(); onClick() }}
              className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-surface-container-highest text-on-surface hover:bg-surface-bright transition-colors"
            >
              {isFinished ? "Review" : "Continue"}
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); onDelete() }}
              className="px-3 py-1.5 text-xs font-semibold rounded-lg border border-error/30 text-error hover:bg-error/10 transition-colors"
            >
              Delete
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function HistoryPage() {
  const navigate = useNavigate()
  const [sessions, setSessions] = useState<SessionListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.listSessions()
      .then(setSessions)
      .finally(() => setLoading(false))
  }, [])

  const finished = useMemo(() => sessions.filter((s) => s.finished_at), [sessions])
  const avgScore = useMemo(() =>
    finished.length
      ? Math.round(finished.reduce((acc, s) => acc + (s.overall_score ?? 0), 0) / finished.length * 10) / 10
      : null,
    [finished]
  )
  const bestScore = useMemo(() =>
    finished.length ? Math.max(...finished.map((s) => s.overall_score ?? 0)) : null,
    [finished]
  )

  async function deleteSession(id: number) {
    if (!window.confirm("Delete this session? This action cannot be undone.")) return
    setBusy(true)
    try {
      await api.deleteSession(id)
      setSessions((prev) => prev.filter((s) => s.id !== id))
    } finally {
      setBusy(false)
    }
  }

  async function clearHistory() {
    if (!window.confirm("Clear all interview history and tracked memory? This cannot be undone.")) return
    setBusy(true)
    try {
      await api.clearSessionsHistory()
      setSessions([])
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="h-screen overflow-hidden flex flex-col bg-background">
      {/* Header */}
      <header className="flex justify-between items-center w-full px-6 py-3 border-b border-border bg-background shrink-0">
        <div className="flex items-center gap-2">
          <img src="/logo.jpg" alt="grillme" className="h-9 w-9 rounded-full" />
          <span className="text-xl font-black tracking-tighter uppercase font-wordmark"><span className="text-on-surface">grill</span><span className="text-primary">me</span></span>
        </div>
        <button
          onClick={() => navigate("/")}
          className="px-4 py-1.5 text-xs font-bold rounded-xl shimmer-gradient text-on-primary hover:opacity-90 transition-opacity flex items-center gap-2"
        >
          <span className="material-symbols-outlined text-sm">add</span>
          New Interview
        </button>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <Sidebar activePage="history" />

        {/* Main */}
        <main className="flex-1 overflow-y-auto no-scrollbar p-6">
          <div className="max-w-3xl mx-auto space-y-6">
            {/* Page title */}
            <div className="flex items-start justify-between gap-3">
              <div>
                <h1 className="text-2xl font-headline font-extrabold tracking-tight text-on-surface">
                  Interview History
                </h1>
                <p className="text-sm text-on-surface-variant mt-1">
                  All your past sessions and scores.
                </p>
              </div>
              <button
                onClick={clearHistory}
                disabled={busy || sessions.length === 0}
                className="px-3 py-1.5 text-xs font-semibold rounded-lg border border-error/30 text-error hover:bg-error/10 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Clear history
              </button>
            </div>

            {/* Stats */}
            {sessions.length > 0 && (
              <div className="grid grid-cols-3 gap-4">
                {[
                  { label: "Total sessions", value: sessions.length, icon: "history" },
                  { label: "Avg score", value: avgScore !== null ? `${avgScore}/10` : "—", icon: "avg_pace" },
                  { label: "Best score", value: bestScore !== null ? `${bestScore}/10` : "—", icon: "emoji_events" },
                ].map(({ label, value, icon }) => (
                  <div key={label} className="bg-surface-container rounded-xl border border-outline-variant/20 p-4 flex items-center gap-3">
                    <span className="material-symbols-outlined text-primary text-2xl" style={{ fontVariationSettings: "'FILL' 1" }}>
                      {icon}
                    </span>
                    <div>
                      <p className="text-xs text-outline uppercase tracking-wider">{label}</p>
                      <p className="text-xl font-headline font-bold text-on-surface">{value}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Session list */}
            {loading ? (
              <div className="flex items-center justify-center py-16 gap-3 text-outline">
                <span className="material-symbols-outlined animate-spin">progress_activity</span>
                Loading sessions…
              </div>
            ) : sessions.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-20 gap-4 text-center">
                <span className="material-symbols-outlined text-6xl text-outline/20" style={{ fontVariationSettings: "'FILL' 1" }}>
                  history
                </span>
                <p className="text-on-surface-variant">No interviews yet.</p>
                <button
                  onClick={() => navigate("/")}
                  className="px-4 py-2 text-sm font-bold rounded-xl shimmer-gradient text-on-primary hover:opacity-90 transition-opacity"
                >
                  Start your first interview
                </button>
              </div>
            ) : (
              <div className="space-y-3">
                {sessions.map((s) => (
                  <SessionCard
                    key={s.id}
                    session={s}
                    onClick={() => navigate(s.finished_at ? `/session/${s.id}/scorecard` : `/session/${s.id}`)}
                    onFeedback={() => navigate(`/session/${s.id}/feedback`)}
                    onDelete={() => deleteSession(s.id)}
                  />
                ))}
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  )
}
