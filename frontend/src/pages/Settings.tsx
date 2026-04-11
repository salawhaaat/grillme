import { useState } from "react"
import { Sidebar } from "@/components/Sidebar"
import { cn } from "@/lib/utils"

interface Settings {
  llmProvider: "openai" | "gemini"
  openaiApiKey: string
  geminiApiKey: string
  defaultDifficulty: "rare" | "medium" | "well_done"
  sessionTimeoutMins: number
  soundEnabled: boolean
  autoScroll: boolean
  voiceOutputEnabled: boolean
  voiceName: "en-US-GuyNeural" | "en-US-JennyNeural" | "en-US-AriaNeural"
  autoSendVoiceInput: boolean
}

const DEFAULTS: Settings = {
  llmProvider: "openai",
  openaiApiKey: "",
  geminiApiKey: "",
  defaultDifficulty: "medium",
  sessionTimeoutMins: 45,
  soundEnabled: false,
  autoScroll: true,
  voiceOutputEnabled: false,
  voiceName: "en-US-GuyNeural",
  autoSendVoiceInput: false,
}

function load(): Settings {
  try {
    const raw = localStorage.getItem("grillme_settings")
    return raw ? { ...DEFAULTS, ...JSON.parse(raw) } : DEFAULTS
  } catch {
    return DEFAULTS
  }
}

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!checked)}
      className={cn(
        "relative w-10 h-5.5 rounded-full border transition-all shrink-0",
        checked
          ? "bg-primary/20 border-primary/40"
          : "bg-surface-container-highest border-outline-variant/30",
      )}
      style={{ height: "1.375rem" }}
    >
      <span
        className={cn(
          "absolute top-0.5 w-4 h-4 rounded-full transition-all",
          checked ? "left-5 bg-primary" : "left-0.5 bg-outline/50",
        )}
      />
    </button>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-surface-container rounded-xl border border-outline-variant/20 overflow-hidden">
      <div className="px-5 py-3 border-b border-outline-variant/20">
        <h2 className="text-xs font-bold text-outline uppercase tracking-wider">{title}</h2>
      </div>
      <div className="divide-y divide-outline-variant/10">{children}</div>
    </div>
  )
}

function Row({ label, description, children }: { label: string; description?: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 px-5 py-4">
      <div>
        <p className="text-sm font-semibold text-on-surface">{label}</p>
        {description && <p className="text-xs text-on-surface-variant mt-0.5">{description}</p>}
      </div>
      {children}
    </div>
  )
}

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings>(load)
  const [saved, setSaved] = useState(false)

  function update<K extends keyof Settings>(key: K, value: Settings[K]) {
    setSettings((prev) => ({ ...prev, [key]: value }))
    setSaved(false)
  }

  function handleSave() {
    localStorage.setItem("grillme_settings", JSON.stringify(settings))
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  function handleReset() {
    setSettings(DEFAULTS)
    localStorage.removeItem("grillme_settings")
    setSaved(false)
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
        <Sidebar activePage="settings" />

        <main className="flex-1 overflow-y-auto no-scrollbar p-6">
          <div className="max-w-2xl mx-auto space-y-6">
            <div>
              <h1 className="text-2xl font-headline font-extrabold tracking-tight text-on-surface">Settings</h1>
              <p className="text-sm text-on-surface-variant mt-1">Configure your grillme experience.</p>
            </div>

            {/* AI Provider */}
            <Section title="AI Provider">
              <Row label="Provider" description="Which AI model powers your interviews">
                {/* Sliding segmented control */}
                <div className="relative flex bg-surface-container rounded-lg p-1 w-40">
                  {/* sliding pill */}
                  <div
                    className="absolute top-1 bottom-1 w-[calc(50%-4px)] rounded-md bg-primary/20 border border-primary/30 transition-transform duration-200 ease-out"
                    style={{ transform: `translateX(${settings.llmProvider === "gemini" ? "calc(100% + 4px)" : "0"})` }}
                  />
                  {(["openai", "gemini"] as const).map((p) => (
                    <button
                      key={p}
                      onClick={() => update("llmProvider", p)}
                      className={cn(
                        "relative z-10 flex-1 py-1.5 text-xs font-semibold capitalize rounded-md transition-colors duration-200",
                        settings.llmProvider === p ? "text-primary" : "text-on-surface-variant hover:text-on-surface",
                      )}
                    >
                      {p}
                    </button>
                  ))}
                </div>
              </Row>
              {/* API key — updates for active provider */}
              <Row
                label="API Key"
                description={
                  settings.llmProvider === "openai"
                    ? "sk-... from platform.openai.com"
                    : "AIza... from aistudio.google.com"
                }
              >
                <div className="relative">
                  <input
                    key={settings.llmProvider}
                    type="password"
                    placeholder={settings.llmProvider === "openai" ? "sk-••••••••" : "AIza••••••••"}
                    value={settings.llmProvider === "openai" ? settings.openaiApiKey : settings.geminiApiKey}
                    onChange={(e) =>
                      update(settings.llmProvider === "openai" ? "openaiApiKey" : "geminiApiKey", e.target.value)
                    }
                    className="w-56 px-3 py-1.5 text-xs rounded-lg border border-primary/30 bg-surface-container-highest text-on-surface placeholder:text-outline/40 focus:outline-none focus:border-primary/60 transition-colors font-mono"
                  />
                  {(settings.llmProvider === "openai" ? settings.openaiApiKey : settings.geminiApiKey) && (
                    <span
                      className="absolute right-2 top-1/2 -translate-y-1/2 material-symbols-outlined text-green-400 text-sm"
                      style={{ fontVariationSettings: "'FILL' 1" }}
                    >
                      check_circle
                    </span>
                  )}
                </div>
              </Row>
            </Section>

            {/* Interview Defaults */}
            <Section title="Interview Defaults">
              <Row label="Default Difficulty" description="Pre-selected cooking level when starting an interview">
                <div className="flex gap-2">
                  {([
                    { key: "rare", icon: "water_drop", color: "text-rose-400 border-rose-400/30 bg-rose-400/10" },
                    { key: "medium", icon: "outdoor_grill", color: "text-amber-400 border-amber-400/30 bg-amber-400/10" },
                    { key: "well_done", icon: "local_fire_department", color: "text-orange-500 border-orange-500/30 bg-orange-500/10" },
                  ] as const).map(({ key, icon, color }) => (
                    <button
                      key={key}
                      onClick={() => update("defaultDifficulty", key)}
                      title={key.replace("_", " ")}
                      className={cn(
                        "w-8 h-8 rounded-lg border flex items-center justify-center transition-all",
                        settings.defaultDifficulty === key
                          ? color
                          : "border-outline-variant/20 text-outline hover:border-outline-variant/40",
                      )}
                    >
                      <span className="material-symbols-outlined text-sm" style={{ fontVariationSettings: "'FILL' 1" }}>
                        {icon}
                      </span>
                    </button>
                  ))}
                </div>
              </Row>

              <Row label="Session Timeout" description="Auto-end session after this many minutes">
                <div className="flex items-center gap-2">
                  <input
                    type="range"
                    min={15}
                    max={120}
                    step={5}
                    value={settings.sessionTimeoutMins}
                    onChange={(e) => update("sessionTimeoutMins", Number(e.target.value))}
                    className="w-24 accent-primary"
                  />
                  <span className="text-sm font-mono text-on-surface w-14 text-right">
                    {settings.sessionTimeoutMins}m
                  </span>
                </div>
              </Row>
            </Section>

            {/* UI Preferences */}
            <Section title="UI Preferences">
              <Row label="Auto-scroll chat" description="Scroll to the latest message automatically">
                <Toggle
                  checked={settings.autoScroll}
                  onChange={(v) => update("autoScroll", v)}
                />
              </Row>
              <Row label="Sound effects" description="Play subtle sounds for message events">
                <Toggle
                  checked={settings.soundEnabled}
                  onChange={(v) => update("soundEnabled", v)}
                />
              </Row>
            </Section>

            <Section title="Voice">
              <Row label="Voice output" description="Play interviewer responses as audio">
                <Toggle
                  checked={settings.voiceOutputEnabled}
                  onChange={(v) => update("voiceOutputEnabled", v)}
                />
              </Row>
              <Row label="Voice selection" description="Pick interviewer voice">
                <select
                  value={settings.voiceName}
                  onChange={(e) => update("voiceName", e.target.value as Settings["voiceName"])}
                  className="px-3 py-1.5 text-xs rounded-lg border border-outline-variant/30 bg-surface-container-highest text-on-surface focus:outline-none"
                >
                  <option value="en-US-GuyNeural">GuyNeural</option>
                  <option value="en-US-JennyNeural">JennyNeural</option>
                  <option value="en-US-AriaNeural">AriaNeural</option>
                </select>
              </Row>
              <Row label="Auto-send voice input" description="Send message automatically when mic stops">
                <Toggle
                  checked={settings.autoSendVoiceInput}
                  onChange={(v) => update("autoSendVoiceInput", v)}
                />
              </Row>
            </Section>

            {/* Actions */}
            <div className="flex gap-3">
              <button
                onClick={handleReset}
                className="flex-1 py-2.5 text-sm font-semibold rounded-xl border border-outline-variant/30 text-on-surface-variant hover:bg-surface-container-high transition-colors"
              >
                Reset to defaults
              </button>
              <button
                onClick={handleSave}
                className={cn(
                  "flex-1 py-2.5 text-sm font-bold rounded-xl transition-all",
                  saved
                    ? "bg-green-500/20 text-green-400 border border-green-500/30"
                    : "shimmer-gradient text-on-primary hover:opacity-90",
                )}
              >
                {saved ? (
                  <span className="flex items-center justify-center gap-2">
                    <span className="material-symbols-outlined text-sm">check_circle</span>
                    Saved
                  </span>
                ) : (
                  "Save settings"
                )}
              </button>
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
