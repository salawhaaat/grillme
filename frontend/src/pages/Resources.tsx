import { useState } from "react"
import { Sidebar } from "@/components/Sidebar"
import { cn } from "@/lib/utils"

interface Resource {
  title: string
  description: string
  tag: string
  href: string
  icon: string
}

const RESOURCES: Resource[] = [
  {
    title: "Big-O Cheat Sheet",
    description: "Time & space complexity for common algorithms and data structures.",
    tag: "Algorithms",
    href: "https://www.bigocheatsheet.com",
    icon: "speed",
  },
  {
    title: "LeetCode Patterns",
    description: "Top 14 coding interview patterns with examples and templates.",
    tag: "Patterns",
    href: "https://seanprashad.com/leetcode-patterns/",
    icon: "pattern",
  },
  {
    title: "System Design Primer",
    description: "Comprehensive guide for system design interviews, covering scalability and architecture.",
    tag: "System Design",
    href: "https://github.com/donnemartin/system-design-primer",
    icon: "architecture",
  },
  {
    title: "Behavioral Interview Guide",
    description: "STAR method, common questions, and how to structure your answers.",
    tag: "Behavioral",
    href: "https://www.levels.fyi/blog/behavioral-interview-guide.html",
    icon: "psychology",
  },
  {
    title: "Blind 75",
    description: "75 LeetCode problems that cover the most important concepts.",
    tag: "Problems",
    href: "https://leetcode.com/discuss/general-discussion/460599/blind-75-leetcode-questions",
    icon: "list_alt",
  },
  {
    title: "NeetCode Roadmap",
    description: "Structured roadmap and video solutions for interview preparation.",
    tag: "Roadmap",
    href: "https://neetcode.io/roadmap",
    icon: "map",
  },
  {
    title: "Tech Interview Handbook",
    description: "Curated interview prep materials for software engineers.",
    tag: "General",
    href: "https://www.techinterviewhandbook.org",
    icon: "menu_book",
  },
  {
    title: "Grokking System Design",
    description: "Interactive guide to system design interview questions.",
    tag: "System Design",
    href: "https://www.educative.io/courses/grokking-the-system-design-interview",
    icon: "hub",
  },
  {
    title: "CP Algorithms",
    description: "Detailed explanations and implementations of algorithms for competitive programming.",
    tag: "Algorithms",
    href: "https://cp-algorithms.com",
    icon: "calculate",
  },
  {
    title: "CTCI (Book)",
    description: "Cracking the Coding Interview — 189 programming questions and solutions.",
    tag: "Books",
    href: "https://www.crackingthecodinginterview.com",
    icon: "auto_stories",
  },
]

const ALL_TAGS = ["All", ...Array.from(new Set(RESOURCES.map((r) => r.tag)))]

export default function ResourcesPage() {
  const [search, setSearch] = useState("")
  const [activeTag, setActiveTag] = useState("All")

  const filtered = RESOURCES.filter((r) => {
    const matchesTag = activeTag === "All" || r.tag === activeTag
    const matchesSearch =
      !search ||
      r.title.toLowerCase().includes(search.toLowerCase()) ||
      r.description.toLowerCase().includes(search.toLowerCase())
    return matchesTag && matchesSearch
  })

  return (
    <div className="h-screen overflow-hidden flex flex-col bg-background">
      <header className="flex justify-between items-center w-full px-6 py-3 border-b border-border bg-background shrink-0">
        <div className="flex items-center gap-2">
          <img src="/logo.jpg" alt="grillme" className="h-9 w-9 rounded-full" />
          <span className="text-xl font-black tracking-tighter uppercase font-wordmark"><span className="text-on-surface">grill</span><span className="text-primary">me</span></span>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <Sidebar activePage="resources" />

        <main className="flex-1 overflow-y-auto no-scrollbar p-6">
          <div className="max-w-3xl mx-auto space-y-6">
            <div>
              <h1 className="text-2xl font-headline font-extrabold tracking-tight text-on-surface">
                Resources
              </h1>
              <p className="text-sm text-on-surface-variant mt-1">
                Curated links for interview preparation.
              </p>
            </div>

            {/* Search + Filter */}
            <div className="flex flex-col gap-3">
              <div className="flex items-center gap-2 px-4 py-2.5 bg-surface-container rounded-xl border border-outline-variant/20">
                <span className="material-symbols-outlined text-outline text-lg">search</span>
                <input
                  className="flex-1 bg-transparent text-sm text-on-surface placeholder:text-outline focus:outline-none"
                  placeholder="Search resources…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
                {search && (
                  <button onClick={() => setSearch("")} className="text-outline hover:text-on-surface transition-colors">
                    <span className="material-symbols-outlined text-sm">close</span>
                  </button>
                )}
              </div>

              <div className="flex gap-2 flex-wrap">
                {ALL_TAGS.map((tag) => (
                  <button
                    key={tag}
                    onClick={() => setActiveTag(tag)}
                    className={cn(
                      "px-3 py-1 text-xs font-semibold rounded-full border transition-colors",
                      activeTag === tag
                        ? "bg-primary/15 text-primary border-primary/30"
                        : "border-outline-variant/30 text-on-surface-variant hover:border-outline-variant/60 hover:text-on-surface",
                    )}
                  >
                    {tag}
                  </button>
                ))}
              </div>
            </div>

            {/* Grid */}
            {filtered.length === 0 ? (
              <div className="py-16 flex flex-col items-center gap-3 text-center">
                <span className="material-symbols-outlined text-5xl text-outline/20">search_off</span>
                <p className="text-on-surface-variant text-sm">No resources found.</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {filtered.map((r) => (
                  <a
                    key={r.href}
                    href={r.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="group bg-surface-container rounded-xl border border-outline-variant/20 hover:border-primary/30 hover:bg-surface-container-high transition-all p-4 flex gap-4 items-start"
                  >
                    <div className="w-9 h-9 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
                      <span className="material-symbols-outlined text-primary text-lg" style={{ fontVariationSettings: "'FILL' 1" }}>
                        {r.icon}
                      </span>
                    </div>
                    <div className="flex-1 min-w-0 space-y-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="text-sm font-bold text-on-surface group-hover:text-primary transition-colors">
                          {r.title}
                        </h3>
                        <span className="px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-widest rounded bg-surface-container-highest text-outline border border-outline-variant/20">
                          {r.tag}
                        </span>
                      </div>
                      <p className="text-xs text-on-surface-variant leading-relaxed">{r.description}</p>
                    </div>
                    <span className="material-symbols-outlined text-sm text-outline/40 group-hover:text-primary/60 transition-colors shrink-0">
                      open_in_new
                    </span>
                  </a>
                ))}
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  )
}
