const BASE = "/api"

// Push saved API key to backend on every page load so the user never has to edit .env
;(function syncConfig() {
  try {
    const raw = localStorage.getItem("grillme_settings")
    if (!raw) return
    const s = JSON.parse(raw) as {
      llmProvider?: string
      openaiApiKey?: string
      geminiApiKey?: string
      groqApiKey?: string
    }
    const provider = s.llmProvider ?? ""
    const key =
      provider === "openai" ? (s.openaiApiKey ?? "") :
      provider === "gemini" ? (s.geminiApiKey ?? "") :
      (s.groqApiKey ?? "")
    if (provider && key) {
      fetch(`${BASE}/config`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider, api_key: key }),
      }).catch(() => {})
    }
  } catch { /* ignore */ }
})()

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

export interface AvatarSessionInfo {
  enabled: boolean
  provider: "local" | "wav2lip"
  persona_seed: string
  reason?: string
}

export interface AvatarSpeakVideoInfo {
  enabled: boolean
  provider: "local" | "wav2lip"
  reason?: string
  video_url?: string
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
  role: "user" | "assistant" | "system"
  content: string
}

export interface AxisScore {
  score: number
  comment: string
}

export interface ScorecardAxes {
  technical_correctness: AxisScore
  process_of_thought: AxisScore
  curiosity: AxisScore
  self_presentation: AxisScore
  closing_questions: AxisScore
  code_quality: AxisScore
}

export interface Scorecard {
  overall_score: number
  axes?: ScorecardAxes
  strengths: string[]
  areas_to_improve: string[]
  recommendation?: string
  summary?: string
  improvements?: string[]
  sections?: ScorecardSection[]
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

async function extractErrorMessage(res: Response): Promise<string> {
  const text = await res.text()
  if (!text) return `HTTP ${res.status}`
  try {
    const json = JSON.parse(text)
    return json.detail ?? json.message ?? text
  } catch {
    return text
  }
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await extractErrorMessage(res))
  return res.json()
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(await extractErrorMessage(res))
  return res.json()
}

async function del<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { method: "DELETE" })
  if (!res.ok) throw new Error(await extractErrorMessage(res))
  return res.json()
}

async function postBlob(path: string): Promise<Blob> {
  const res = await fetch(`${BASE}${path}`, { method: "POST" })
  if (!res.ok) throw new Error(await extractErrorMessage(res))
  return res.blob()
}

async function postBlobJson(path: string, body: unknown): Promise<Blob> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await extractErrorMessage(res))
  return res.blob()
}

function normalizeScorecard(raw: RawScorecard | null): Scorecard | null {
  if (!raw || typeof raw.overall_score !== "number") return null
  const areasToImprove = raw.areas_to_improve ?? raw.improvements ?? []
  return {
    overall_score: raw.overall_score,
    axes: raw.axes,
    strengths: Array.isArray(raw.strengths) ? raw.strengths : [],
    areas_to_improve: Array.isArray(areasToImprove) ? areasToImprove : [],
    recommendation: raw.recommendation,
    summary: raw.summary,
    improvements: Array.isArray(raw.improvements) ? raw.improvements : [],
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
    cv_text?: string,
  ) =>
    post<CreateSessionResponse>("/sessions/create", { source, content, difficulty, cv_text }),

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

  getAvatarSession: (id: number) =>
    get<AvatarSessionInfo>(`/avatar/session/${id}`),

  getAvatarSpeakVideo: (id: number, text: string) =>
    post<AvatarSpeakVideoInfo>(`/avatar/session/${id}/speak-video`, { text }),

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

  runCode: (code: string, stdin_input = "") =>
    post<RunResult>("/code/run", { code, stdin_input }),

  runTests: (code: string, session_id: number) =>
    post<TestResult>("/code/test", { code, session_id }),

  shareCode: (
    session_id: number,
    code: string,
    run_result?: RunResult | null,
    test_result?: TestResult | null,
  ) =>
    post<{ ok: boolean }>("/code/share", { session_id, code, run_result: run_result ?? undefined, test_result: test_result ?? undefined }),

  speakSession: (sessionId: number, voice?: string) =>
    postBlob(
      `/voice/speak-session/${sessionId}${
        voice ? `?voice=${encodeURIComponent(voice)}` : ""
      }`,
    ),

  speakText: (text: string, voice?: string) =>
    postBlobJson("/voice/speak-text", {
      text,
      ...(voice ? { voice } : {}),
    }),

  saveConfig: (provider: string, apiKey: string) =>
    post<{ ok: boolean }>("/config", { provider, api_key: apiKey }),
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
  if (!res.ok || !res.body) throw new Error(await extractErrorMessage(res))
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    yield decoder.decode(value, { stream: true })
  }
}

export interface RunResult {
  stdout: string
  stderr: string
  exit_code: number
  runtime_ms: number
  timed_out: boolean
}

export interface TestCaseResult {
  id: number
  passed: boolean
  input: string
  expected: string
  actual: string
  error: string | null
}

export interface TestResult {
  passed: number
  failed: number
  total: number
  results: TestCaseResult[]
  runtime_ms: number
}
