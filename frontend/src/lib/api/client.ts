const BASE = "/api"

export type Difficulty = "rare" | "medium" | "well_done"
export type SessionSource = "jd" | "url" | "text"

export interface CreateSessionResponse {
  session_id: number
  source: SessionSource
  difficulty: Difficulty
  company: string | null
  role: string | null
  level: string | null
  problem: {
    title: string
    difficulty: string
    statement: string
    method_name: string
  }
  starter_code: string
  opening_message: string
}

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
  cv_text: string | null
  problem_url: string | null
  problem_statement: string | null
  starter_code: string | null
  test_cases: {
    method_name: string
    test_cases: Array<{ input: unknown[]; expected: unknown }>
  } | null
  method_name: string | null
  scorecard: Scorecard | null
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
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
  total_tokens: number
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

type RawScorecard = Partial<Scorecard> & {
  overall_score?: number
  strengths?: string[]
  improvements?: string[]
  areas_to_improve?: string[]
  recommendation?: string
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

async function del<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { method: "DELETE" })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
  return res.json()
}

function normalizeScorecard(raw: RawScorecard | null): Scorecard | null {
  if (!raw || typeof raw.overall_score !== "number") return null
  const improvements = raw.improvements ?? raw.areas_to_improve ?? []
  const summary =
    raw.summary ??
    (raw.recommendation ? `Recommendation: ${raw.recommendation.replace(/_/g, " ")}` : "Interview completed.")
  return {
    overall_score: raw.overall_score,
    summary,
    strengths: Array.isArray(raw.strengths) ? raw.strengths : [],
    improvements: Array.isArray(improvements) ? improvements : [],
    sections: Array.isArray(raw.sections) ? raw.sections : [],
  }
}

function normalizeSession(session: Session): Session {
  return {
    ...session,
    scorecard: normalizeScorecard(session.scorecard as RawScorecard | null),
  }
}

export const api = {
  createSession: (
    source: SessionSource,
    content: string,
    difficulty: Difficulty = "medium",
  ) =>
    post<CreateSessionResponse>("/sessions/create", { source, content, difficulty }),

  createSessionFromJD: (
    jd: string,
    difficulty: Difficulty = "medium",
    cv_text?: string,
  ) =>
    post<SessionInfo>("/sessions/from-jd", { jd, difficulty, cv_text }),

  createFromProblem: (problem_url: string, difficulty: Difficulty = "medium") =>
    post<ProblemSessionInfo>("/sessions/from-problem", { problem_url, difficulty }),

  listSessions: () =>
    get<SessionListItem[]>("/sessions/"),

  getSession: async (id: number) =>
    normalizeSession(await get<Session>(`/sessions/${id}`)),

  getUserMemory: () =>
    get<UserWeakness[]>("/sessions/memory"),

  deleteSession: (id: number) =>
    del<{ deleted_session_id: number }>(`/sessions/${id}`),

  clearSessionsHistory: () =>
    del<{ deleted_sessions: number; deleted_memory_rows: number }>("/sessions/"),

  finishSession: async (id: number) => {
    const res = await post<{ scorecard: RawScorecard }>(`/sessions/${id}/finish`, {})
    const normalized = normalizeScorecard(res.scorecard)
    if (!normalized) {
      throw new Error("Invalid scorecard payload")
    }
    return { scorecard: normalized }
  },
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
