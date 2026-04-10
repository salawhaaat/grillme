const BASE = "/api"

export type Difficulty = "rare" | "medium" | "well_done"

export interface SessionInfo {
  session_id: number
  company: string | null
  role: string | null
  level: string | null
  difficulty: Difficulty
  opening_message: string
  prep_plan?: string
}

export interface ProblemSessionInfo {
  session_id: number
  problem_title: string
  problem_difficulty: string
  difficulty: Difficulty
  opening_message: string
}

export interface Session {
  id: number
  mode: string
  difficulty: Difficulty
  company: string | null
  role: string | null
  level: string | null
  persona: string | null
  prep_plan: string | null
  problem_url: string | null
  scorecard: Scorecard | null
  messages: Message[]
  created_at: string
  finished_at: string | null
}

export interface SessionListItem {
  id: number
  mode: string
  difficulty: Difficulty
  company: string | null
  role: string | null
  level: string | null
  overall_score: number | null
  message_count: number
  created_at: string
  finished_at: string | null
}

export interface Message {
  role: "user" | "assistant"
  content: string
}

export interface Scorecard {
  overall_score: number
  summary: string
  strengths: string[]
  improvements: string[]
  sections: ScorecardSection[]
}

export interface ScorecardSection {
  name: string
  score: number
  feedback: string
}

export interface UserWeakness {
  area: string
  frequency: number
  last_session_id: number | null
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
  return res.json()
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
  return res.json()
}

export const api = {
  createSessionFromJD: (jd: string, difficulty: Difficulty = "medium") =>
    post<SessionInfo>("/sessions/from-jd", { jd, difficulty: difficulty }),

  createFromProblem: (problem_url: string, difficulty: Difficulty = "medium") =>
    post<ProblemSessionInfo>("/sessions/from-problem", { problem_url, difficulty }),

  listSessions: () =>
    get<SessionListItem[]>("/sessions/"),

  getSession: (id: number) =>
    get<Session>(`/sessions/${id}`),

  getUserMemory: () =>
    get<UserWeakness[]>("/sessions/memory"),

  finishSession: (id: number) =>
    post<{ scorecard: Scorecard }>(`/sessions/${id}/finish`, {}),
}

export async function* streamMessage(
  sessionId: number,
  content: string,
): AsyncGenerator<string> {
  const res = await fetch(`${BASE}/sessions/${sessionId}/message`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  })
  if (!res.ok || !res.body) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    yield decoder.decode(value, { stream: true })
  }
}
