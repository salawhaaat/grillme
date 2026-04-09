import { useState, useEffect, useRef } from "react"
import { Sidebar } from "@/components/Sidebar"
import { cn } from "@/lib/utils"

interface Note {
  id: string
  title: string
  content: string
  updatedAt: number
}

function newNote(): Note {
  return { id: crypto.randomUUID(), title: "Untitled", content: "", updatedAt: Date.now() }
}

function load(): Note[] {
  try {
    const raw = localStorage.getItem("grillme_notes")
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

function save(notes: Note[]) {
  localStorage.setItem("grillme_notes", JSON.stringify(notes))
}

export default function NotesPage() {
  const [notes, setNotes] = useState<Note[]>(() => {
    const existing = load()
    return existing.length ? existing : [newNote()]
  })
  const [activeId, setActiveId] = useState<string>(() => {
    const existing = load()
    return existing.length ? existing[0].id : notes[0]?.id ?? ""
  })
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const active = notes.find((n) => n.id === activeId) ?? notes[0]

  function updateActive(patch: Partial<Note>) {
    setNotes((prev) => {
      const updated = prev.map((n) =>
        n.id === activeId ? { ...n, ...patch, updatedAt: Date.now() } : n
      )
      if (saveTimer.current) clearTimeout(saveTimer.current)
      saveTimer.current = setTimeout(() => save(updated), 500)
      return updated
    })
  }

  function addNote() {
    const n = newNote()
    setNotes((prev) => {
      const updated = [n, ...prev]
      save(updated)
      return updated
    })
    setActiveId(n.id)
  }

  function deleteNote(id: string) {
    setNotes((prev) => {
      const updated = prev.filter((n) => n.id !== id)
      const next = updated.length ? updated : [newNote()]
      save(next)
      if (id === activeId) setActiveId(next[0].id)
      return next
    })
  }

  useEffect(() => {
    return () => { if (saveTimer.current) clearTimeout(saveTimer.current) }
  }, [])

  const fmt = (ts: number) =>
    new Date(ts).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })

  return (
    <div className="h-screen overflow-hidden flex flex-col bg-background">
      <header className="flex justify-between items-center w-full px-6 py-3 border-b border-border bg-background shrink-0">
        <div className="flex items-center gap-2">
          <img src="/logo.jpg" alt="grillme" className="h-9 w-9 rounded-full" />
          <span className="text-xl font-black tracking-tighter uppercase font-wordmark"><span className="text-on-surface">grill</span><span className="text-primary">me</span></span>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <Sidebar activePage="notes" />

        {/* Notes list */}
        <div className="w-64 flex flex-col border-r border-border bg-surface-container-low shrink-0">
          <div className="flex items-center justify-between px-4 py-3 border-b border-border">
            <span className="text-xs font-bold uppercase tracking-widest text-outline">Notes</span>
            <button
              onClick={addNote}
              className="w-6 h-6 rounded-lg bg-primary/10 text-primary flex items-center justify-center hover:bg-primary/20 transition-colors"
            >
              <span className="material-symbols-outlined text-sm">add</span>
            </button>
          </div>
          <div className="flex-1 overflow-y-auto no-scrollbar">
            {notes.map((n) => (
              <button
                key={n.id}
                onClick={() => setActiveId(n.id)}
                className={cn(
                  "w-full text-left px-4 py-3 border-b border-border/50 group transition-colors",
                  n.id === activeId
                    ? "bg-primary/10 border-l-2 border-l-primary"
                    : "hover:bg-surface-container",
                )}
              >
                <p className={cn(
                  "text-xs font-semibold truncate",
                  n.id === activeId ? "text-primary" : "text-on-surface"
                )}>
                  {n.title || "Untitled"}
                </p>
                <p className="text-[10px] text-outline mt-0.5 truncate">{fmt(n.updatedAt)}</p>
                {n.id === activeId && (
                  <button
                    onClick={(e) => { e.stopPropagation(); deleteNote(n.id) }}
                    className="opacity-0 group-hover:opacity-100 mt-1 text-[10px] text-error hover:underline transition-opacity"
                  >
                    delete
                  </button>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Editor */}
        <main className="flex-1 flex flex-col overflow-hidden">
          {active && (
            <>
              <div className="px-8 pt-6 pb-3 border-b border-border shrink-0">
                <input
                  className="w-full bg-transparent text-2xl font-headline font-extrabold text-on-surface tracking-tight focus:outline-none placeholder:text-outline/30"
                  value={active.title}
                  onChange={(e) => updateActive({ title: e.target.value })}
                  placeholder="Note title…"
                />
                <p className="text-[10px] text-outline mt-1">{fmt(active.updatedAt)}</p>
              </div>
              <textarea
                className="flex-1 px-8 py-5 bg-transparent font-mono text-sm text-on-surface placeholder:text-outline/30 resize-none focus:outline-none leading-relaxed no-scrollbar"
                value={active.content}
                onChange={(e) => updateActive({ content: e.target.value })}
                placeholder="Start writing…"
              />
            </>
          )}
        </main>
      </div>
    </div>
  )
}
