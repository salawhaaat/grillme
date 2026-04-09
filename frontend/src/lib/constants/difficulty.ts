import type { Difficulty } from "@/lib/api/client"

export const DIFFICULTY_META: Record<
  Difficulty,
  { label: string; color: string; icon: string }
> = {
  rare:      { label: "Rare",      color: "text-rose-400 bg-rose-400/10 border-rose-400/20",       icon: "water_drop" },
  medium:    { label: "Medium",    color: "text-amber-400 bg-amber-400/10 border-amber-400/20",    icon: "outdoor_grill" },
  well_done: { label: "Well Done", color: "text-orange-500 bg-orange-500/10 border-orange-500/20", icon: "local_fire_department" },
}

export const DIFFICULTY_PICKER_META: Record<
  Difficulty,
  { label: string; desc: string; icon: string; color: string; active: string }
> = {
  rare: {
    label: "Rare",
    desc: "Hints when stuck",
    icon: "water_drop",
    color: "border-outline-variant/20 text-outline hover:border-rose-400/40 hover:text-rose-400",
    active: "border-rose-400/50 bg-rose-400/5 text-rose-400",
  },
  medium: {
    label: "Medium",
    desc: "Hint on request",
    icon: "outdoor_grill",
    color: "border-outline-variant/20 text-outline hover:border-amber-400/40 hover:text-amber-400",
    active: "border-amber-400/50 bg-amber-400/5 text-amber-400",
  },
  well_done: {
    label: "Well Done",
    desc: "No mercy",
    icon: "local_fire_department",
    color: "border-outline-variant/20 text-outline hover:border-orange-500/40 hover:text-orange-500",
    active: "border-orange-500/50 bg-orange-500/5 text-orange-500",
  },
}
