import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function scoreColorText(score: number): string {
  return score >= 8 ? "text-green-400" : score >= 6 ? "text-tertiary" : "text-error"
}

export function scoreColorBg(score: number): string {
  return score >= 8 ? "bg-green-500" : score >= 6 ? "bg-tertiary" : "bg-error"
}
