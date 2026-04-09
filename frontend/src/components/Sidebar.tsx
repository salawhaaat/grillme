import { useNavigate } from "react-router-dom"
import { cn } from "@/lib/utils"

export type Page = "home" | "history" | "notes" | "whiteboard" | "resources" | "settings" | "profile"

const NAV_ITEMS: { icon: string; label: string; page: Page; path: string }[] = [
  { icon: "description", label: "Problem", page: "home", path: "/" },
  { icon: "sticky_note_2", label: "Notes", page: "notes", path: "/notes" },
  { icon: "draw", label: "Whiteboard", page: "whiteboard", path: "/whiteboard" },
  { icon: "history", label: "History", page: "history", path: "/history" },
  { icon: "menu_book", label: "Resources", page: "resources", path: "/resources" },
]

const BOTTOM_ITEMS: { icon: string; label: string; page: Page; path: string }[] = [
  { icon: "settings", label: "Settings", page: "settings", path: "/settings" },
  { icon: "person", label: "Profile", page: "profile", path: "/profile" },
]

interface SidebarProps {
  activePage: Page
}

export function Sidebar({ activePage }: SidebarProps) {
  const navigate = useNavigate()

  function NavButton({ icon, label, page, path }: { icon: string; label: string; page: Page; path: string }) {
    const active = activePage === page
    return (
      <button
        onClick={() => navigate(path)}
        className={cn(
          "flex flex-col items-center gap-1 w-full py-3 transition-all duration-100 relative",
          active
            ? "text-primary before:absolute before:left-0 before:h-8 before:w-1 before:bg-primary before:rounded-r-full"
            : "text-outline hover:text-on-surface hover:bg-surface-container-low",
        )}
      >
        <span
          className="material-symbols-outlined text-xl"
          style={active ? { fontVariationSettings: "'FILL' 1" } : undefined}
        >
          {icon}
        </span>
        <span className="text-[9px] font-semibold uppercase tracking-widest font-label">
          {label}
        </span>
      </button>
    )
  }

  return (
    <aside className="flex flex-col items-center py-5 h-full w-20 bg-background border-r border-border shrink-0">
      <div className="flex flex-col items-center gap-1 w-full">
        {NAV_ITEMS.map((item) => (
          <NavButton key={item.label} {...item} />
        ))}
      </div>

      <div className="mt-auto flex flex-col items-center gap-1 w-full">
        {BOTTOM_ITEMS.map((item) => (
          <NavButton key={item.label} {...item} />
        ))}
      </div>
    </aside>
  )
}
