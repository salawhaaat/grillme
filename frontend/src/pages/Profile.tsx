import { useState, useEffect, useMemo } from "react"
import { useNavigate } from "react-router-dom"
import { api, type SessionListItem, type UserWeakness } from "@/lib/api/client"
import { cn, scoreColorText } from "@/lib/utils"
import { DIFFICULTY_META } from "@/lib/constants/difficulty"
import { Sidebar } from "@/components/Sidebar"

function StatCard({ label, value, icon }: { label: string; value: string | number; icon: string }) {
  return (
    <div className="bg-surface-container rounded-xl border border-outline-variant/20 p-4 flex items-center gap-3">
      <span className="material-symbols-outlined text-primary text-2xl" style={{ fontVariationSettings: "'FILL' 1" }}>
        {icon}
      </span>
      <div>
        <p className="text-xs text-outline uppercase tracking-wider">{label}</p>
        <p className="text-xl font-headline font-bold text-on-surface">{value}</p>
      </div>
    </div>
  )
}

export default function ProfilePage() {
  const navigate = useNavigate()
  const [sessions, setSessions] = useState<SessionListItem[]>([])
  const [weaknesses, setWeaknesses] = useState<UserWeakness[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([api.listSessions(), api.getUserMemory()])
      .then(([sessionData, memoryData]) => {
        setSessions(sessionData)
        setWeaknesses(memoryData)
      })
      .finally(() => setLoading(false))
  }, [])

  const finished = useMemo(() => sessions.filter((s) => s.finished_at && s.overall_score !== null), [sessions])
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

  const diffCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const s of finished) {
      counts[s.difficulty] = (counts[s.difficulty] ?? 0) + 1
    }
    return counts
  }, [finished])

  const recentSessions = useMemo(() => sessions.slice(0, 5), [sessions])
  const finishedScores = useMemo(
    () =>
      [...finished]
        .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
        .map((s) => s.overall_score ?? 0),
    [finished],
  )
  const topWeaknesses = useMemo(() => weaknesses.slice(0, 3), [weaknesses])

  function weaknessPillClass(freq: number) {
    if (freq >= 3) return "bg-error/20 border-error/40 text-error"
    if (freq === 2) return "bg-warning/20 border-warning/40 text-warning"
    return "bg-outline-variant/20 border-outline-variant/40 text-on-surface-variant"
  }

  function scoreBarColor(score: number) {
    if (score >= 7) return "bg-green-500/80"
    if (score >= 5) return "bg-yellow-500/80"
    return "bg-red-500/80"
  }

  return (
    <div className="h-screen overflow-hidden flex flex-col bg-background">
      <header className="flex justify-between items-center w-full px-6 py-3 border-b border-border bg-background shrink-0">
        <div className="flex items-center gap-2">
          <img src="/logo.jpg" alt="grillme" className="h-9 w-9 rounded-full" />
          <span className="text-xl font-black tracking-tighter uppercase font-wordmark"><span className="text-on-surface">grill</span><span className="text-primary">me</span></span>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <Sidebar activePage="profile" />

        <main className="flex-1 overflow-y-auto no-scrollbar p-6">
          <div className="max-w-2xl mx-auto space-y-6">
            {/* Avatar + name */}
            <div className="flex items-center gap-5">
              <div className="w-16 h-16 rounded-full bg-gradient-to-br from-primary/30 to-primary-container/30 border-2 border-primary/30 flex items-center justify-center">
                <span className="material-symbols-outlined text-3xl text-primary" style={{ fontVariationSettings: "'FILL' 1" }}>
                  person
                </span>
              </div>
              <div>
                <h1 className="text-2xl font-headline font-extrabold tracking-tight text-on-surface">
                  Your Profile
                </h1>
                <p className="text-sm text-on-surface-variant mt-0.5">
                  {sessions.length} session{sessions.length !== 1 ? "s" : ""} total
                </p>
              </div>
            </div>

            {/* Stats grid */}
            {loading ? (
              <div className="flex items-center justify-center py-10 gap-3 text-outline">
                <span className="material-symbols-outlined animate-spin">progress_activity</span>
                Loading stats…
              </div>
            ) : (
              <>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <StatCard label="Sessions" value={sessions.length} icon="history" />
                  <StatCard label="Completed" value={finished.length} icon="check_circle" />
                  <StatCard label="Avg Score" value={avgScore !== null ? `${avgScore}/10` : "—"} icon="avg_pace" />
                  <StatCard label="Best Score" value={bestScore !== null ? `${bestScore}/10` : "—"} icon="emoji_events" />
                </div>

                {/* Difficulty breakdown */}
                {finished.length > 0 && (
                  <div className="bg-surface-container rounded-xl border border-outline-variant/20 p-5">
                    <h2 className="text-xs font-bold text-outline uppercase tracking-wider mb-4">
                      Difficulty Breakdown
                    </h2>
                    <div className="space-y-3">
                      {(["rare", "medium", "well_done"] as const).map((d) => {
                        const count = diffCounts[d] ?? 0
                        const pct = finished.length ? (count / finished.length) * 100 : 0
                        const meta = DIFFICULTY_META[d]
                        return (
                          <div key={d} className="space-y-1">
                            <div className="flex items-center justify-between text-xs">
                              <span className={cn("font-semibold flex items-center gap-1.5", meta.color.split(" ")[0])}>
                                <span className="material-symbols-outlined text-sm" style={{ fontVariationSettings: "'FILL' 1" }}>
                                  {meta.icon}
                                </span>
                                {meta.label}
                              </span>
                              <span className="text-outline font-mono">{count} session{count !== 1 ? "s" : ""}</span>
                            </div>
                            <div className="h-1.5 rounded-full bg-surface-container-highest overflow-hidden">
                              <div
                                className={cn("h-full rounded-full transition-all duration-700", meta.color.split(" ")[1]?.replace("bg-", "bg-") ?? "bg-primary")}
                                style={{ width: `${pct}%`, backgroundColor: "currentColor" }}
                              />
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}

                {/* Recent sessions */}
                {recentSessions.length > 0 && (
                  <div className="bg-surface-container rounded-xl border border-outline-variant/20 overflow-hidden">
                    <div className="px-5 py-3 border-b border-outline-variant/20 flex items-center justify-between">
                      <h2 className="text-xs font-bold text-outline uppercase tracking-wider">Recent Sessions</h2>
                      <button
                        onClick={() => navigate("/history")}
                        className="text-xs text-primary hover:underline"
                      >
                        View all
                      </button>
                    </div>
                    <div className="divide-y divide-outline-variant/10">
                      {recentSessions.map((s) => {
                        const diff = DIFFICULTY_META[s.difficulty]
                        return (
                          <button
                            key={s.id}
                            onClick={() => navigate(s.finished_at ? `/session/${s.id}/scorecard` : `/session/${s.id}`)}
                            className="w-full flex items-center justify-between px-5 py-3 hover:bg-surface-container-high transition-colors text-left gap-4"
                          >
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-semibold text-on-surface truncate">
                                {s.role ?? "Unknown Role"}
                                {s.company && <span className="font-normal text-on-surface-variant"> @ {s.company}</span>}
                              </p>
                              <div className="flex items-center gap-2 mt-0.5">
                                <span className={cn("text-[10px] font-bold", diff.color.split(" ")[0])}>
                                  {diff.label}
                                </span>
                                <span className="text-[10px] text-outline">
                                  {new Date(s.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                                </span>
                              </div>
                            </div>
                            {s.overall_score !== null ? (
                              <span className={cn("text-xl font-black font-headline tabular-nums shrink-0", scoreColorText(s.overall_score))}>
                                {s.overall_score}<span className="text-xs font-normal text-outline">/10</span>
                              </span>
                            ) : (
                              <span className="text-xs text-outline font-mono shrink-0">—</span>
                            )}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                )}

                <div className="bg-surface-container rounded-xl border border-outline-variant/20 p-5 space-y-4">
                  <h2 className="text-xs font-bold text-outline uppercase tracking-wider">
                    Weak Areas
                  </h2>
                  {weaknesses.length === 0 ? (
                    <p className="text-sm text-on-surface-variant">
                      Complete interviews to start tracking your growth areas
                    </p>
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      {weaknesses.map((w) => (
                        <span
                          key={w.area}
                          className={cn(
                            "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs border font-semibold",
                            weaknessPillClass(w.frequency),
                          )}
                        >
                          <span>{w.area}</span>
                          <span className="font-mono">{w.frequency}</span>
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                <div className="bg-surface-container rounded-xl border border-outline-variant/20 p-5 space-y-4">
                  <h2 className="text-xs font-bold text-outline uppercase tracking-wider">
                    Score Trend
                  </h2>
                  {finishedScores.length === 0 ? (
                    <p className="text-sm text-on-surface-variant">No completed sessions yet.</p>
                  ) : (
                    <div className="space-y-2">
                      <div className="flex items-end gap-1 h-24">
                        {finishedScores.map((s, i) => (
                          <div
                            key={i}
                            className={cn("w-6 rounded-t", scoreBarColor(s))}
                            style={{ height: `${(s / 10) * 100}%` }}
                            title={`Session ${i + 1}: ${s}/10`}
                          />
                        ))}
                      </div>
                      <div className="flex items-center gap-1 text-[10px] text-outline">
                        {finishedScores.map((_, i) => (
                          <span key={i} className="w-6 text-center">{i + 1}</span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                <div className="bg-surface-container rounded-xl border border-outline-variant/20 p-5 space-y-2">
                  <h2 className="text-xs font-bold text-outline uppercase tracking-wider">
                    Improvement Areas
                  </h2>
                  {topWeaknesses.length === 0 ? (
                    <p className="text-sm text-on-surface-variant">
                      Keep finishing interviews to get personalized focus recommendations.
                    </p>
                  ) : (
                    <p className="text-sm text-on-surface-variant leading-relaxed">
                      Focus for next session:{" "}
                      <span className="text-on-surface font-semibold">
                        {topWeaknesses.map((w) => w.area).join(", ")}
                      </span>
                      .
                    </p>
                  )}
                </div>

                {sessions.length === 0 && (
                  <div className="flex flex-col items-center justify-center py-20 gap-4 text-center">
                    <span className="material-symbols-outlined text-6xl text-outline/20" style={{ fontVariationSettings: "'FILL' 1" }}>
                      person
                    </span>
                    <p className="text-on-surface-variant">No interviews yet.</p>
                    <button
                      onClick={() => navigate("/")}
                      className="px-4 py-2 text-sm font-bold rounded-xl shimmer-gradient text-on-primary hover:opacity-90 transition-opacity"
                    >
                      Start your first interview
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        </main>
      </div>
    </div>
  )
}
